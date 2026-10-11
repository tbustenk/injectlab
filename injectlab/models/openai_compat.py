"""A LOCAL OpenAI-compatible chat adapter (LM Studio, Ollama, llama.cpp server).

This is the free/offline counterpart to the Anthropic adapter: a real model
decides the actions, but it runs on your own machine so there is no cost and no
data leaves the box. It speaks the same JSON text protocol as every other
adapter (see protocol.py) and plugs into the identical agent loop, policy path,
and oracles -- only the decision-maker changes.

It is NOT Claude and uses NO model SDK. It is stdlib urllib hitting a local HTTP
port that happens to speak the OpenAI `/v1/chat/completions` wire format, which
is simply how these local servers expose a loaded model. One adapter therefore
serves them all; point `base_url` at whichever is running:

  - LM Studio   http://localhost:1234/v1   (default)
  - Ollama      http://localhost:11434/v1
  - llama.cpp   http://localhost:8080/v1

Determinism caveat for the write-up: temperature defaults to 0, but a local
model at temperature 0 is still not perfectly reproducible across loads/builds,
and a single sample is not an estimate of its behaviour distribution.

NOTE: constructing this adapter makes no network call. Only `next_action` does,
and only when the agent actually runs.
"""

import json
import urllib.error
import urllib.request

from .base import AgentContext, ModelAdapter

# LM Studio's default local server. Override base_url for Ollama / llama.cpp.
DEFAULT_BASE_URL = "http://localhost:1234/v1"


class OpenAICompatAdapter(ModelAdapter):
    name = "local-openai"

    def __init__(self, model: str = "local-model", *,
                 base_url: str = DEFAULT_BASE_URL, api_key: str | None = None,
                 max_tokens: int = 1024, temperature: float = 0.0,
                 timeout: float = 300.0, no_think: bool = False):
        self.model = model
        self.name = f"local:{model}"
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key  # local servers normally need none
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Local models can be slow (large models, first-load, CPU offload), so
        # the default timeout is generous compared with a hosted API.
        self.timeout = timeout
        # no_think appends the Qwen-style /no_think tag so a reasoning model
        # answers directly. It makes "thinking disabled" reproducible in the
        # tool rather than relying on a server UI toggle.
        self.no_think = no_think

    def next_action(self, ctx: AgentContext) -> str:
        messages = _to_messages(ctx)
        if self.no_think and messages:
            messages[0]["content"] += "\n/no_think"
        request_body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }
        headers = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_body).encode(), method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"Local model server error {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            # Almost always: the local server isn't running or is on another port.
            raise RuntimeError(
                f"Could not reach a local OpenAI-compatible server at "
                f"{self.base_url}. Is LM Studio (or Ollama) running and a model "
                f"loaded? ({e.reason})") from e

        return _first_message(payload)


def list_models(base_url: str = DEFAULT_BASE_URL, *, timeout: float = 5.0) -> list[str]:
    """Ask a local server which models it is serving (GET /models).

    Used by `injectlab doctor` to confirm reachability before a run and to show
    the exact model id to pass to --model. Raises an actionable RuntimeError if
    the server cannot be reached.
    """
    req = urllib.request.Request(f"{base_url.rstrip('/')}/models", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        raise RuntimeError(
            f"Could not reach a local OpenAI-compatible server at {base_url}. "
            f"Is LM Studio (or Ollama) running with the server started? "
            f"({reason})") from e
    return [m.get("id", "") for m in payload.get("data", [])]


def _to_messages(ctx: AgentContext) -> list[dict]:
    """Replay the run so far as OpenAI chat messages.

    The hardened prompt is a real `system` message; the user states the task;
    each past step becomes the assistant's action JSON followed by the tool
    result as a user turn. The model's next completion is the next action.
    """
    messages = [
        {"role": "system", "content": ctx.system_prompt},
        {"role": "user", "content": ctx.user_request},
    ]
    for step in ctx.transcript:
        if step.status == "invalid":
            # Replay the model's actual (unparseable) reply, then the correction.
            messages.append({"role": "assistant",
                             "content": step.action.args.get("raw", "")})
            messages.append({"role": "user", "content": step.result})
            continue
        action_json = json.dumps({"tool": step.action.tool,
                                  "args": dict(step.action.args)})
        messages.append({"role": "assistant", "content": action_json})
        messages.append({"role": "user",
                         "content": f"Tool result ({step.status}): {step.result}"})
    return messages


def _first_message(payload: dict) -> str:
    """Pull the assistant text out of a chat-completions response."""
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"No choices in response: {payload!r}")
    content = choices[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise RuntimeError(f"No message content in response: {payload!r}")
    return content

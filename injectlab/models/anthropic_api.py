"""A real Claude adapter over the Messages API, using only the standard library.

This is the Stage-7 bridge from the labelled mock to a real model. It speaks the
same JSON text protocol as every other adapter (see protocol.py): it is handed
the context so far and must return raw text that parses to one action. The agent
loop, policy path, and oracles are then identical to the mock's — the only thing
that changes is who decides the next action.

Design choices, all consistent with the repo conventions:
  - stdlib only (urllib). The project ships no model SDK; adapters are stdlib.
  - temperature 0 for a reproducible first run. This collapses sampling variance
    to near zero, so the paired design's common-random-numbers reduce to the
    per-cell canary. That is a LIMITATION to state in the write-up: real-world
    deployments run at nonzero temperature, and a single temperature-0 sample is
    not an estimate of the model's behaviour distribution. Revisit with k
    samples per cell at a chosen temperature when we want variance.
  - the API key is read from ANTHROPIC_API_KEY and never logged or committed.

NOTE: constructing this adapter makes no network call. Only `next_action` does,
and only when the agent actually runs. Nothing here runs at import time.
"""

import json
import os
import urllib.error
import urllib.request

from .base import AgentContext, ModelAdapter

_ENDPOINT = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

# The cheapest current Claude model (see the claude-api reference). Haiku 4.5
# still accepts `temperature`, so temperature-0 determinism is available here.
DEFAULT_MODEL = "claude-haiku-4-5"

# Models that reject the `temperature` parameter (a 400). For these the param is
# omitted; they do not offer sampling-temperature control, so the temperature-0
# reproducibility claim does not apply to them.
_TEMPERATURE_UNSUPPORTED = (
    "claude-opus-4-7", "claude-opus-4-8",
    "claude-sonnet-5", "claude-fable-5", "claude-mythos-5",
)


class AnthropicAdapter(ModelAdapter):
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, *, api_key: str | None = None,
                 max_tokens: int = 1024, temperature: float = 0.0,
                 timeout: float = 60.0):
        self.model = model
        self.name = f"anthropic:{model}"
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

    def next_action(self, ctx: AgentContext) -> str:
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; a real run needs a key.")

        request_body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": ctx.system_prompt,
            "messages": _to_messages(ctx),
        }
        # Only send `temperature` to models that accept it; the rest 400 on it.
        if any(self.model.startswith(p) for p in _TEMPERATURE_UNSUPPORTED):
            if self.temperature != 0.0:
                raise RuntimeError(
                    f"{self.model} does not accept a temperature; got "
                    f"temperature={self.temperature}. Leave it at the default.")
        else:
            request_body["temperature"] = self.temperature

        req = urllib.request.Request(_ENDPOINT, data=json.dumps(request_body).encode(),
                                     method="POST", headers={
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # The body carries the API's error detail; it never echoes the key.
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"Anthropic API error {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            # Network-level failure (DNS, connection refused, timeout).
            raise RuntimeError(
                f"Could not reach the Anthropic API: {e.reason}") from e

        return _first_text(payload)


def _to_messages(ctx: AgentContext) -> list[dict]:
    """Replay the run so far as Messages-API turns.

    The user states the task; each past step becomes the assistant's action (the
    JSON it emitted) followed by the tool's result as a user turn. The model's
    next completion is the next action.
    """
    messages: list[dict] = [{"role": "user", "content": ctx.user_request}]
    for step in ctx.transcript:
        action_json = json.dumps({"tool": step.action.tool,
                                  "args": dict(step.action.args)})
        messages.append({"role": "assistant", "content": action_json})
        messages.append({"role": "user",
                         "content": f"Tool result ({step.status}): {step.result}"})
    return messages


def _first_text(payload: dict) -> str:
    """Pull the first text block out of a Messages-API response."""
    for block in payload.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    raise RuntimeError(f"No text block in response: {payload!r}")

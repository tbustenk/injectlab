"""AnthropicAdapter tests. No network: urlopen is monkeypatched.

These prove the adapter builds the right request and plugs into the agent loop
exactly like the mock, without ever calling the real API.
"""

import io
import json

import pytest

from injectlab import AnthropicAdapter, parse_action
from injectlab.models.base import AgentContext, Step
from injectlab.protocol import Action


def _fake_response(text):
    body = json.dumps({"content": [{"type": "text", "text": text}]}).encode()
    return io.BytesIO(body)


def test_builds_request_and_returns_action_text(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode())
        return _fake_response('{"tool": "finish", "args": {"response": "ok"}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    adapter = AnthropicAdapter(api_key="test-key")
    ctx = AgentContext("SYS", "do the task", transcript=[])
    raw = adapter.next_action(ctx)

    # The returned text parses to an action, like every other adapter.
    assert parse_action(raw).tool == "finish"
    # Request shape: endpoint, auth header, model, temperature 0, system prompt.
    assert captured["url"].endswith("/v1/messages")
    assert captured["headers"]["x-api-key"] == "test-key"
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["system"] == "SYS"
    assert captured["body"]["messages"][0] == {"role": "user", "content": "do the task"}


def test_transcript_becomes_assistant_and_user_turns(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _fake_response('{"tool": "finish", "args": {}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    step = Step(Action("read_document", {"name": "report.txt"}), "the text", "executed")
    ctx = AgentContext("SYS", "summarise 'report.txt'", transcript=[step])
    AnthropicAdapter(api_key="k").next_action(ctx)

    msgs = captured["body"]["messages"]
    # user request, then the prior action as assistant, then its result as user.
    assert msgs[0]["role"] == "user"
    assert json.loads(msgs[1]["content"]) == {
        "tool": "read_document", "args": {"name": "report.txt"}}
    assert msgs[2]["role"] == "user" and "the text" in msgs[2]["content"]


def test_missing_key_raises_without_network(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    adapter = AnthropicAdapter(api_key=None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        adapter.next_action(AgentContext("SYS", "task", transcript=[]))

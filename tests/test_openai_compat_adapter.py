"""Local OpenAI-compatible adapter tests. No network: urlopen is monkeypatched.

These prove the adapter builds a correct chat-completions request against a
LOCAL server and plugs into the agent loop exactly like every other adapter,
without ever opening a socket.
"""

import io
import json

import pytest

from injectlab import OpenAICompatAdapter, parse_action
from injectlab.models.base import AgentContext, Step
from injectlab.protocol import Action


def _fake_response(text):
    body = json.dumps({"choices": [{"message": {"role": "assistant",
                                                 "content": text}}]}).encode()
    return io.BytesIO(body)


def test_builds_local_request_and_returns_action_text(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = json.loads(req.data.decode())
        return _fake_response('{"tool": "finish", "args": {"response": "ok"}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    adapter = OpenAICompatAdapter(model="llama-3.1-8b")
    ctx = AgentContext("SPOT", "do the task", transcript=[])
    raw = adapter.next_action(ctx)

    assert parse_action(raw).tool == "finish"
    # Local endpoint, chat-completions shape, system + user seeded.
    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["body"]["model"] == "llama-3.1-8b"
    assert captured["body"]["temperature"] == 0.0
    assert captured["body"]["messages"][0] == {"role": "system", "content": "SPOT"}
    assert captured["body"]["messages"][1] == {"role": "user", "content": "do the task"}
    # A local server needs no key, so no auth header is sent.
    assert "authorization" not in captured["headers"]


def test_base_url_is_configurable_for_ollama(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _fake_response('{"tool": "finish", "args": {}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    OpenAICompatAdapter(base_url="http://localhost:11434/v1").next_action(
        AgentContext("S", "t", transcript=[]))
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"


def test_api_key_adds_bearer_header_when_given(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        return _fake_response('{"tool": "finish", "args": {}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    OpenAICompatAdapter(api_key="sk-local").next_action(
        AgentContext("S", "t", transcript=[]))
    assert captured["headers"]["authorization"] == "Bearer sk-local"


def test_transcript_becomes_assistant_and_user_turns(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data.decode())
        return _fake_response('{"tool": "finish", "args": {}}')

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    step = Step(Action("read_document", {"name": "report.txt"}), "the text", "executed")
    ctx = AgentContext("S", "summarise 'report.txt'", transcript=[step])
    OpenAICompatAdapter().next_action(ctx)

    msgs = captured["body"]["messages"]
    assert msgs[0]["role"] == "system" and msgs[1]["role"] == "user"
    assert json.loads(msgs[2]["content"]) == {
        "tool": "read_document", "args": {"name": "report.txt"}}
    assert msgs[3]["role"] == "user" and "the text" in msgs[3]["content"]


def test_unreachable_server_gives_an_actionable_error(monkeypatch):
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(RuntimeError, match="Is LM Studio"):
        OpenAICompatAdapter().next_action(AgentContext("S", "t", transcript=[]))


def test_empty_choices_raises(monkeypatch):
    def empty(req, timeout=None):
        return io.BytesIO(json.dumps({"choices": []}).encode())

    monkeypatch.setattr("urllib.request.urlopen", empty)
    with pytest.raises(RuntimeError, match="No choices"):
        OpenAICompatAdapter().next_action(AgentContext("S", "t", transcript=[]))

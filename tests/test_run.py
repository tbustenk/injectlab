"""Run-harness tests. The mock path runs offline; the paid path is never hit.

These pin the honesty behaviour: a mock run writes report + JSON but never a
write-up paste block, the provenance records simulation=True, model selection
builds the right adapter without a network call, and a hosted run refuses to do
anything until explicitly confirmed.
"""

import json

from injectlab import AnthropicAdapter, MockModel, OpenAICompatAdapter
from injectlab.run import _make_model_factory, _model_name, execute, rescore


def test_mock_run_writes_html_and_json_but_no_writeup(tmp_path):
    r = execute(mode="mock", out=str(tmp_path), when="2026-10-11")
    assert r["status"] == "ok"
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "results.json").exists()
    # Mock numbers are never promoted to the public write-up.
    assert not (tmp_path / "writeup_section.md").exists()

    data = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert data["provenance"]["simulation"] is True
    assert data["provenance"]["model_name"] == "mock"
    assert data["provenance"]["split"] == "test"
    assert len(data["arms"]) == len(data["provenance"]["arms"]) >= 6
    assert data["by_technique"], "technique breakdown should be recorded"


def test_factory_selection_builds_the_right_adapter_without_network():
    assert isinstance(_make_model_factory("mock", None, None, 0.0)(), MockModel)
    assert isinstance(
        _make_model_factory("local", "m", "http://localhost:1234/v1", 0.0)(),
        OpenAICompatAdapter)
    assert isinstance(
        _make_model_factory("anthropic", "claude-haiku-4-5", None, 0.0)(),
        AnthropicAdapter)


def test_model_name_labels():
    assert _model_name("mock", None) == "mock"
    assert _model_name("local", "llama-3.1-8b") == "local:llama-3.1-8b"
    assert _model_name("anthropic", "claude-haiku-4-5") == "claude-haiku-4-5"


def test_anthropic_without_confirmation_runs_nothing(tmp_path, capsys):
    r = execute(mode="anthropic", model="claude-haiku-4-5",
                out=str(tmp_path), assume_yes=False, when="2026-10-11")
    assert r["status"] == "needs-confirmation"
    # No run means no outputs and no network call.
    assert not (tmp_path / "report.html").exists()
    out = capsys.readouterr().out
    assert "$" in out and "No API call" in out  # the estimate was shown first


def test_run_persists_raw_logs_and_rescore_reproduces(tmp_path):
    r = execute(mode="mock", quick=True, out=str(tmp_path), when="2026-10-11",
                show_progress=False)
    runs = tmp_path / "runs.jsonl"
    assert runs.exists(), "a run must persist raw per-run logs for re-scoring"
    lines = [ln for ln in runs.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines and r["written"].get("runs")

    before = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    rr = rescore(out=str(tmp_path))
    assert rr["status"] == "ok" and rr["n_records"] == len(lines)
    after = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))

    # Same oracle over the same logs -> identical per-arm executed counts.
    be = {a["arm"]: a["executed"] for a in before["arms"]}
    ae = {a["arm"]: a["executed"] for a in after["arms"]}
    assert be == ae
    assert after["provenance"]["rescored"] is True


def test_local_run_writes_a_writeup_paste_block(tmp_path, monkeypatch):
    # Drive the "local" path offline by making the local adapter behave like the
    # mock (returns canned actions); proves a non-mock run emits writeup_section.md.
    import io

    def fake_urlopen(req, timeout=None):
        import json as _json
        body = _json.loads(req.data.decode())
        used = [_json.loads(m["content"]).get("tool")
                for m in body["messages"] if m["role"] == "assistant"]
        if "read_document" not in used:
            act = {"tool": "read_document", "args": {"name": "report.txt"}}
        else:
            act = {"tool": "finish", "args": {"response": "Summary: ok"}}
        return io.BytesIO(_json.dumps(
            {"choices": [{"message": {"content": _json.dumps(act)}}]}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    r = execute(mode="local", model="fake-local", out=str(tmp_path),
                when="2026-10-11")
    assert r["status"] == "ok"
    assert (tmp_path / "writeup_section.md").exists()
    section = (tmp_path / "writeup_section.md").read_text(encoding="utf-8")
    assert "local:fake-local" in section
    assert "paired p vs baseline" in section and "baseline" in section

"""CLI + doctor + --quick tests. No network: urlopen is monkeypatched."""

import io
import json

import pytest

from injectlab.cli import main
from injectlab.run import execute


def _models_response(ids):
    body = json.dumps({"data": [{"id": i} for i in ids]}).encode()
    return io.BytesIO(body)


def test_doctor_lists_loaded_models(monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout=None: _models_response(["qwen3-27b"]))
    main(["doctor"])
    out = capsys.readouterr().out
    assert "reachable" in out
    assert "qwen3-27b" in out
    # Hands the user the exact next command.
    assert "run --mode local --model qwen3-27b" in out


def test_doctor_reports_unreachable_server(monkeypatch):
    import urllib.error

    def boom(req, timeout=None):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(SystemExit, match="Is LM Studio"):
        main(["doctor"])


def test_quick_shrinks_the_grid(tmp_path):
    # Full grid is 5 techniques x 6 mutations x 3 positions = 90; quick is
    # 5 techniques x 1 x 1 = 5 attack cells per arm.
    r = execute(mode="mock", quick=True, out=str(tmp_path),
                when="2026-10-11", show_progress=False)
    assert r["status"] == "ok" and r["n"] == 5


def test_cli_run_mock_writes_outputs(tmp_path):
    main(["run", "--out", str(tmp_path), "--quick"])
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "results.json").exists()

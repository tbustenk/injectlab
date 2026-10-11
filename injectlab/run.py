"""Drive the measurement grid against a chosen model and write real outputs.

This is the one entry point that runs a REAL model, so it owns the honesty
gates and nothing else:

  - a cost estimate + explicit confirmation before any PAID hosted run;
  - full provenance (model, date, n, split, arms, git commit, simulation flag)
    saved beside the numbers so every result is traceable;
  - a model-stamped report, so mock output can never be mistaken for findings;
  - results written only to the gitignored output dir (default results/).

It adds no measurement logic: same grid, oracle, and stats as `measure`. For a
non-mock run it also drops a paste-ready Markdown block (writeup_section.md) so a
human promotes the numbers into docs/writeup.md in a reviewed commit -- a script
never edits the public write-up.

    python -m injectlab.run                         # mock (free, offline)
    python -m injectlab.run --mode local --model llama-3.1-8b-instruct
    python -m injectlab.run --mode anthropic --model claude-haiku-4-5   # asks first
"""

import json
from dataclasses import asdict
from pathlib import Path

from .agent import RunResult
from .cost import estimate_cost, format_estimate
from .corpus import load_corpus
from .measure import (
    ARMS,
    CellOutcome,
    UTILITY_TOKEN,
    breakdown,
    build_cells,
    format_breakdown,
    format_report,
    run_grid,
    summarise,
)
from .models.anthropic_api import DEFAULT_MODEL as ANTHROPIC_DEFAULT
from .models.anthropic_api import AnthropicAdapter
from .models.mock import MockModel
from .models.openai_compat import DEFAULT_BASE_URL, OpenAICompatAdapter
from .oracles import score_security, score_utility
from .report_html import format_html
from .tools import Message, ToolCall


def _make_model_factory(mode, model, base_url, temperature, timeout=None,
                        no_think=False):
    if mode == "mock":
        return lambda: MockModel()
    if mode == "local":
        kw = {"model": model, "base_url": base_url, "temperature": temperature,
              "no_think": no_think}
        if timeout is not None:
            kw["timeout"] = timeout
        return lambda: OpenAICompatAdapter(**kw)
    if mode == "anthropic":
        kw = {"model": model, "temperature": temperature}
        if timeout is not None:
            kw["timeout"] = timeout
        return lambda: AnthropicAdapter(**kw)
    raise ValueError(f"unknown mode {mode!r}")


def _model_name(mode, model):
    if mode == "mock":
        return "mock"
    if mode == "local":
        return f"local:{model}"
    return model  # anthropic: the bare model id


def _git_commit():
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:
        return None


def _fmt(k, n, ci):
    rate = k / n if n else 0.0
    return f"{rate:.0%} [{ci[0]:.0%}, {ci[1]:.0%}]"


def _writeup_section(reports, *, model_name, when, temperature, n):
    """A paste-ready docs/writeup.md section 4 table, filled from real numbers."""
    lines = [
        f"**Model:** {model_name}  **Date:** {when}  "
        f"**Temperature:** {temperature}  **n (cells):** {n}",
        "",
        "| Arm | n | executed [95% CI] | attempted [95% CI] | "
        "structural [95% CI] | benign ok | paired p vs baseline |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        p = "—" if r.p_value is None else f"{r.p_value:.4f}"
        benign = "yes" if r.benign_completed else "NO"
        lines.append(
            f"| {r.arm} | {r.n} | {_fmt(r.executed, r.n, r.executed_ci)} | "
            f"{_fmt(r.attempted, r.n, r.attempted_ci)} | "
            f"{_fmt(r.attempted_structural, r.n, r.structural_ci)} | "
            f"{benign} | {p} |")
    return "\n".join(lines)


def execute(*, mode="mock", model=None, base_url=DEFAULT_BASE_URL, out="results",
            temperature=0.0, when=None, assume_yes=False, quick=False,
            show_progress=True, timeout=None, no_think=False, max_steps=None):
    """Run the grid under `mode` and write outputs. Returns a status dict.

    For mode="anthropic" without assume_yes, prints the cost estimate and returns
    {"status": "needs-confirmation"} WITHOUT running anything (no network).

    quick=True runs a demo-sized subset (one mutation x one position) so a run
    against a slow local model finishes in a few minutes; the full grid is the
    default for real numbers.
    """
    if when is None:
        from datetime import date
        when = date.today().isoformat()
    if mode == "local" and not model:
        model = "local-model"
    if mode == "anthropic" and not model:
        model = ANTHROPIC_DEFAULT

    carrier, seeds = load_corpus()
    if quick:
        # Smallest grid that still exercises every technique and every arm.
        cells = build_cells(carrier, seeds, mutations=["identity"],
                            positions=("end",))
    else:
        cells = build_cells(carrier, seeds)

    if mode == "anthropic":
        # Charter: a dollar figure ALWAYS precedes a paid run, by any entry path.
        print(format_estimate(estimate_cost(carrier, cells, ARMS, model)))
        if not assume_yes:
            print("\nPaid run NOT confirmed. Re-run with --yes to proceed; "
                  "nothing was run.")
            return {"status": "needs-confirmation"}

    name = _model_name(mode, model)
    factory = _make_model_factory(mode, model, base_url, temperature,
                                  timeout=timeout, no_think=no_think)

    def _progress(done, total, cell_id):
        print(f"  [{done + 1}/{total}] {cell_id}", flush=True)

    records = []

    def _collect(scenario, arm, canary, allowed, result):
        records.append(_record_dict(scenario, arm, canary, allowed, result))

    if show_progress:
        print(f"Running {len(cells)} cells x {len(ARMS)} arms against {name} ...")
    outcomes = run_grid(carrier, cells, model_factory=factory,
                        on_cell=_progress if show_progress else None,
                        on_record=_collect, max_steps=max_steps)

    provenance = {
        "tool": "injectlab", "mode": mode, "model_name": name,
        "base_url": base_url if mode == "local" else None,
        "temperature": temperature, "date": when, "split": "test",
        "arms": list(ARMS), "git_commit": _git_commit(),
        "simulation": mode == "mock",
    }
    written = _emit(outcomes, out=out, name=name, when=when,
                    temperature=temperature, provenance=provenance,
                    write_writeup=(mode != "mock"))

    # Raw per-run logs, so an oracle change can be re-scored offline (injectlab
    # rescore) without paying for the model again. They hold canaries, so they
    # live only in the gitignored results dir.
    runs_path = Path(out) / "runs.jsonl"
    runs_path.write_text("".join(json.dumps(r) + "\n" for r in records),
                         encoding="utf-8")
    written["runs"] = str(runs_path)

    print(f"\nWrote: {', '.join(written.values())}")
    if mode == "mock":
        print("(SIMULATION: mock numbers are not findings about any real model.)")
    else:
        print("Paste results/writeup_section.md into docs/writeup.md section 4 "
              "when you have reviewed the numbers.")
    return {"status": "ok", "written": written, "model_name": name,
            "n": outcomes and summarise(outcomes)[0].n or 0}


def _emit(outcomes, *, out, name, when, temperature, provenance,
          write_writeup) -> dict:
    """Write report.html + results.json (+ writeup paste block) and print them.

    Shared by a live run and by `rescore`, so both produce identical artefacts.
    """
    reports = summarise(outcomes)
    tech = breakdown(outcomes, by="technique")
    n = reports[0].n if reports else 0

    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    written = {}

    html = format_html(reports, tech, model_name=name, when=when,
                       temperature=temperature)
    (outdir / "report.html").write_text(html, encoding="utf-8")
    written["html"] = str(outdir / "report.html")

    results = {"provenance": {**provenance, "n_attack_cells_per_arm": n},
               "arms": [asdict(r) for r in reports],
               "by_technique": [asdict(r) for r in tech]}
    (outdir / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    written["json"] = str(outdir / "results.json")

    # Mock numbers are never promoted to the public write-up, so no paste block.
    if write_writeup:
        section = _writeup_section(reports, model_name=name, when=when,
                                   temperature=temperature, n=n)
        (outdir / "writeup_section.md").write_text(section, encoding="utf-8")
        written["writeup"] = str(outdir / "writeup_section.md")

    print(format_report(reports, model_name=name))
    print()
    print(format_breakdown(tech, model_name=name))
    return written


def _record_dict(scenario, arm, canary, allowed, result) -> dict:
    return {
        "cell_id": scenario.id, "arm": arm, "is_attack": scenario.is_attack,
        "technique": scenario.technique, "position": scenario.position,
        "canary": canary, "allowed": sorted(allowed),
        "stop_reason": result.stop_reason, "final_response": result.final_response,
        "tool_log": [{"tool": c.tool, "args": c.args, "result": c.result,
                      "status": c.status} for c in result.tool_log],
        "outbox": [{"to": m.to, "body": m.body} for m in result.outbox],
    }


def _replay(rec) -> RunResult:
    tool_log = [ToolCall(c["tool"], dict(c["args"]), c["result"], c["status"])
                for c in rec["tool_log"]]
    outbox = [Message(m["to"], m["body"]) for m in rec["outbox"]]
    return RunResult(rec["canary"], rec.get("final_response"), [], tool_log,
                     outbox, rec["stop_reason"])


def rescore(out="results") -> dict:
    """Re-score a saved run's raw logs with the CURRENT oracle, no model calls.

    Reads results/runs.jsonl (and results/results.json for provenance), re-runs
    the oracle, and rewrites report.html + results.json. This is how an oracle
    change is re-evaluated against real data without paying to run again.
    """
    outdir = Path(out)
    runs_path = outdir / "runs.jsonl"
    if not runs_path.exists():
        raise RuntimeError(f"no saved runs at {runs_path}; run first.")
    records = [json.loads(line) for line in
               runs_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    prov = {}
    results_path = outdir / "results.json"
    if results_path.exists():
        prov = json.loads(results_path.read_text(encoding="utf-8")).get(
            "provenance", {})
    name = prov.get("model_name", "rescored")
    when = prov.get("date")
    temperature = prov.get("temperature")

    outcomes = []
    for rec in records:
        result = _replay(rec)
        sec = score_security(result, rec["canary"],
                             frozenset(rec.get("allowed", [])))
        util = score_utility(result, expect_substring=UTILITY_TOKEN)
        outcomes.append(CellOutcome(
            rec["cell_id"], rec["arm"], rec["is_attack"],
            sec.executed, sec.attempted, sec.attempted_structural,
            util.completed, rec.get("technique"), rec.get("position")))

    provenance = {**prov, "rescored": True}
    written = _emit(outcomes, out=out, name=name, when=when,
                    temperature=temperature, provenance=provenance,
                    write_writeup=not prov.get("simulation", False))
    print(f"\nRe-scored {len(records)} runs. Wrote: {', '.join(written.values())}")
    return {"status": "ok", "written": written, "n_records": len(records)}


def main(argv=None):  # pragma: no cover - `python -m injectlab.run` -> `injectlab run`
    import sys
    from .cli import main as cli_main
    cli_main(["run", *(argv if argv is not None else sys.argv[1:])])


if __name__ == "__main__":  # pragma: no cover
    main()

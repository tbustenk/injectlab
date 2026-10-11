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

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .cost import estimate_cost, format_estimate
from .corpus import load_corpus
from .measure import (
    ARMS,
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
from .report_html import format_html

MODES = ("mock", "local", "anthropic")


def _make_model_factory(mode, model, base_url, temperature):
    if mode == "mock":
        return lambda: MockModel()
    if mode == "local":
        return lambda: OpenAICompatAdapter(
            model=model, base_url=base_url, temperature=temperature)
    if mode == "anthropic":
        return lambda: AnthropicAdapter(model=model, temperature=temperature)
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
            temperature=0.0, when=None, assume_yes=False):
    """Run the grid under `mode` and write outputs. Returns a status dict.

    For mode="anthropic" without assume_yes, prints the cost estimate and returns
    {"status": "needs-confirmation"} WITHOUT running anything (no network).
    """
    if when is None:
        from datetime import date
        when = date.today().isoformat()
    if mode == "local" and not model:
        model = "local-model"
    if mode == "anthropic" and not model:
        model = ANTHROPIC_DEFAULT

    carrier, seeds = load_corpus()
    cells = build_cells(carrier, seeds)

    if mode == "anthropic" and not assume_yes:
        print(format_estimate(estimate_cost(carrier, cells, ARMS, model)))
        print("\nPaid run NOT confirmed. Re-run with --yes to proceed; "
              "nothing was run.")
        return {"status": "needs-confirmation"}

    name = _model_name(mode, model)
    factory = _make_model_factory(mode, model, base_url, temperature)
    outcomes = run_grid(carrier, cells, model_factory=factory)
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

    results = {
        "provenance": {
            "tool": "injectlab",
            "mode": mode,
            "model_name": name,
            "base_url": base_url if mode == "local" else None,
            "temperature": temperature,
            "date": when,
            "split": "test",
            "n_attack_cells_per_arm": n,
            "arms": list(ARMS),
            "git_commit": _git_commit(),
            "simulation": mode == "mock",
        },
        "arms": [asdict(r) for r in reports],
        "by_technique": [asdict(r) for r in tech],
    }
    (outdir / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")
    written["json"] = str(outdir / "results.json")

    # Mock numbers are never promoted to the public write-up, so no paste block.
    if mode != "mock":
        section = _writeup_section(reports, model_name=name, when=when,
                                   temperature=temperature, n=n)
        (outdir / "writeup_section.md").write_text(section, encoding="utf-8")
        written["writeup"] = str(outdir / "writeup_section.md")

    print(format_report(reports, model_name=name))
    print()
    print(format_breakdown(tech, model_name=name))
    print(f"\nWrote: {', '.join(written.values())}")
    if mode == "mock":
        print("(SIMULATION: mock numbers are not findings about any real model.)")
    else:
        print("Paste results/writeup_section.md into docs/writeup.md section 4 "
              "when you have reviewed the numbers.")
    return {"status": "ok", "written": written, "model_name": name, "n": n}


def main(argv=None):  # pragma: no cover - thin CLI wrapper around execute()
    p = argparse.ArgumentParser(
        prog="python -m injectlab.run",
        description="Run the injectlab grid against a model and write results/.")
    p.add_argument("--mode", choices=MODES, default="mock",
                   help="mock (default, free/offline), local (LM Studio/Ollama), "
                        "or anthropic (hosted, paid).")
    p.add_argument("--model", default=None,
                   help="model id (local: the loaded model; anthropic: e.g. "
                        "claude-haiku-4-5).")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"local server base URL (default {DEFAULT_BASE_URL}).")
    p.add_argument("--out", default="results", help="output directory.")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--yes", action="store_true",
                   help="confirm a paid hosted run (skip the prompt).")
    args = p.parse_args(argv)

    assume_yes = args.yes
    if args.mode == "anthropic" and not assume_yes:
        # Show the estimate, then ask interactively.
        execute(mode="anthropic", model=args.model, out=args.out,
                temperature=args.temperature, assume_yes=False)
        try:
            ans = input("Proceed with the paid run? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Aborted; nothing was run.")
            return
        assume_yes = True

    execute(mode=args.mode, model=args.model, base_url=args.base_url,
            out=args.out, temperature=args.temperature, assume_yes=assume_yes)


if __name__ == "__main__":  # pragma: no cover
    main()

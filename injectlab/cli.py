"""The `injectlab` command: one entry point with subcommands.

    injectlab doctor                       check a local model server
    injectlab run                          mock grid (free, offline)
    injectlab run --mode local --model M   run a local model (LM Studio/Ollama)
    injectlab run --mode anthropic ...     hosted (asks first, then needs --yes)

This is a thin wrapper over run.execute() and the local-server probe; it holds
no measurement logic. `python -m injectlab` and `python -m injectlab.run` both
route here.
"""

import argparse

from .models.openai_compat import DEFAULT_BASE_URL, list_models
from .run import execute, rescore

MODES = ("mock", "local", "anthropic")


def _cmd_run(args):
    assume_yes = args.yes
    if args.mode == "anthropic" and not assume_yes:
        # execute() prints the cost estimate and runs nothing; then we ask.
        execute(mode="anthropic", model=args.model, out=args.out,
                temperature=args.temperature, quick=args.quick,
                timeout=args.timeout, no_think=args.no_think,
                assume_yes=False, show_progress=False)
        try:
            ans = input("Proceed with the paid run? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans not in ("y", "yes"):
            print("Aborted; nothing was run.")
            return
        assume_yes = True

    try:
        execute(mode=args.mode, model=args.model, base_url=args.base_url,
                out=args.out, temperature=args.temperature, quick=args.quick,
                timeout=args.timeout, no_think=args.no_think,
                max_steps=args.max_steps, assume_yes=assume_yes)
    except RuntimeError as e:
        # Common case: local server down or key unset. The message is already
        # actionable; show it, not a traceback.
        raise SystemExit(f"Run failed: {e}")


def _cmd_rescore(args):
    try:
        rescore(out=args.out)
    except RuntimeError as e:
        raise SystemExit(f"rescore: {e}")


def _cmd_doctor(args):
    try:
        models = list_models(args.base_url)
    except RuntimeError as e:
        raise SystemExit(f"doctor: {e}")
    print(f"Local server reachable at {args.base_url}")
    if models:
        print("Loaded model(s):")
        for m in models:
            print(f"  - {m}")
        print(f"\nReady. Run:\n  injectlab run --mode local --model {models[0]}")
    else:
        print("Reachable, but no model is loaded. Load one in LM Studio first.")


def _build_parser():
    p = argparse.ArgumentParser(
        prog="injectlab",
        description="Measure indirect prompt injection against a tool-using agent.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the grid and write results/")
    r.add_argument("--mode", choices=MODES, default="mock",
                   help="mock (default, free/offline), local (LM Studio/Ollama), "
                        "or anthropic (hosted, paid).")
    r.add_argument("--model", default=None,
                   help="model id (local: the loaded model; anthropic: e.g. "
                        "claude-haiku-4-5).")
    r.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"local server base URL (default {DEFAULT_BASE_URL}).")
    r.add_argument("--out", default="results", help="output directory.")
    r.add_argument("--temperature", type=float, default=0.0)
    r.add_argument("--quick", action="store_true",
                   help="demo-sized subset (1 mutation x 1 position) so a slow "
                        "local run finishes in minutes.")
    r.add_argument("--timeout", type=float, default=None,
                   help="per-call timeout in seconds (local models can be slow; "
                        "default 300 for local).")
    r.add_argument("--no-think", action="store_true",
                   help="send the Qwen-style /no_think tag so a reasoning model "
                        "answers directly (faster, cleaner for tool use).")
    r.add_argument("--max-steps", type=int, default=None,
                   help="override the agent step budget (lower = faster runs).")
    r.add_argument("--yes", action="store_true",
                   help="confirm a paid hosted run (skip the prompt).")
    r.set_defaults(func=_cmd_run)

    d = sub.add_parser("doctor", help="check a local model server is reachable")
    d.add_argument("--base-url", default=DEFAULT_BASE_URL,
                   help=f"local server base URL (default {DEFAULT_BASE_URL}).")
    d.set_defaults(func=_cmd_doctor)

    rs = sub.add_parser("rescore",
                        help="re-score saved run logs with the current oracle")
    rs.add_argument("--out", default="results",
                    help="directory holding runs.jsonl (default results).")
    rs.set_defaults(func=_cmd_rescore)

    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()

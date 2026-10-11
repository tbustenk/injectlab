# injectlab

A measurement harness for **indirect prompt injection** against tool-using LLM
agents. It answers one question:

> When an agent reads content an attacker can influence, how often does the
> attacker get it to do something the user never asked for — and which defenses
> actually change that number?

This is a **measurement tool, not an exploit kit**. Everything targets a fake
agent in a fake environment; attacker addresses use reserved TLDs (`.test`,
`.example`) and point nowhere real.

## How it works (end to end)

injectlab runs the *same* attack against an agent many times — with and without
each defense — and counts what gets through. One pass looks like this:

```
  corpus seed ──(× mutation × position)──▶ document with an injection hidden in it
   (a labelled                                   │
    injection)        user's benign request ─────┤  (the injection is untrusted content)
                                                 ▼
                                          ┌──────────────┐
                 defense wraps the agent ▶│    agent     │  reads the doc, decides actions
                (persuade / filter /      │  (a model)   │  over a simple JSON protocol
                 constrain / stacked)     └──────────────┘
                                                 │ tools: read_document · read_secret · send_message
                                                 ▼
                                            tool log  ─────▶  ┌────────┐   deterministic, no LLM judge:
                                                              │ oracle │   attempted / executed / structural
                                                              └────────┘   + did the benign task still work?
                                                 │
                                                 ▼
                                       ┌────────┐   Wilson 95% intervals,
                                       │ stats  │   paired McNemar vs baseline
                                       └────────┘
                                                 ▼
                              report:  text table · per-technique heatmap · self-contained HTML
```

1. **Plant.** Each corpus *seed* is one injection, labelled by technique
   (authority, urgency, social-proof, …). It's dropped into an otherwise-benign
   document at a position (start/middle/end) and re-spelled by a mutation (case,
   synonyms, zero-width, homoglyph, delimiters). One **seed × mutation ×
   position = one cell**. Mutations are fuzzing for language: a defense that
   blocks only one phrasing hasn't been shown to work.
2. **Run.** A fake agent gets the user's innocent request ("summarise this
   document") plus the document, and chooses actions over a plain JSON protocol
   using three tools — read the document (untrusted input), read a secret
   (private data), send a message (outbound channel: the "lethal trifecta"). The
   secret is a fresh per-run **canary**, so a leak is a string match, not an
   opinion.
3. **Defend.** Each run is wrapped by one defense family, or none:
   *persuade* (a hardened prompt), *filter* (strip exfil destinations from what
   the agent reads), *constrain* (least-privilege policy + egress DLP at the
   tool boundary) — plus a *stacked* combination.
4. **Score.** A deterministic **oracle** reads the tool log — no LLM-as-judge.
   It records whether the attack was *attempted* (canary headed outbound),
   *executed* (it actually left), or *structural* (addressed to a recipient the
   user never authorised), and whether the benign task still completed. Security
   and utility are always reported together.
5. **Compare.** Every defense faces the *identical* cells (a paired design;
   randomness comes from the cell, never the defense), so baseline and defense
   meet the same attack. Rates carry 95% **Wilson** intervals; each defense is
   compared to baseline with an exact **McNemar** test.
6. **Report.** A plain-text table, a per-technique heatmap, and a self-contained
   HTML page (dark by default).

The model plugged into step 2 is swappable: a **labelled mock** (free, for CI —
its numbers are *never* findings), a **local open-weights model** via LM Studio
or Ollama, or a **hosted model**. Same pipeline, same oracle, same stats — only
the decision-maker changes.

## What's here

| Piece | Module | What it does |
|---|---|---|
| Target agent | `injectlab/agent.py`, `tools.py` | A deterministic agent with three trifecta tools over a JSON text protocol. |
| Canary | `injectlab/canary.py` | A fresh per-run secret, so a leak is a string match, not an opinion. |
| Oracles | `injectlab/oracles.py` | Deterministic scoring: `attempted` vs `executed` vs structural attempt, plus utility. No LLM judge. |
| Corpus + mutations | `corpus/seeds.yaml`, `injectlab/corpus.py`, `mutations.py` | Labelled injection seeds, deterministic language mutations, dev/test split. |
| Defenses | `injectlab/defenses.py` | Three families — persuade (prompt), filter (sanitise input), constrain (least-privilege policy, egress DLP). |
| Measurement | `injectlab/measure.py`, `stats.py` | Paired grid, Wilson 95% intervals, exact McNemar test, per-technique/position breakdown. |
| HTML report | `injectlab/report_html.py` | A self-contained, dependency-free results page (aggregate table + heatmap). |
| Models | `injectlab/models/` | A labelled mock (CI), a stdlib Claude adapter, and a stdlib local OpenAI-compatible adapter. |
| Cost | `injectlab/cost.py` | A pre-run dollar estimate, shown before any paid hosted run. |

## Install & test

```
pip install -e ".[dev]"
python -m pytest
```

Python 3.10+. Runtime dependency: PyYAML only; all model adapters use the
standard library.

## Run it

**Mock (free, offline).** Prints the aggregate table and the per-technique
heatmap, then writes a standalone HTML page to `results/` (gitignored):

```
python -m injectlab.measure        # text table + heatmap
python -m injectlab.report_html    # writes results/report.html
```

The mock is a labelled **simulation** for CI. Because it keys on the exfil
destination and ignores the persuasion, every technique behaves identically —
its heatmap is deliberately flat. **Its numbers are not findings about any real
model.**

**Against a real local model (LM Studio / Ollama).** Load an instruct model and
start the local server (LM Studio: *Developer → Start Server*, default
`:1234`; Ollama serves `:11434/v1`), then drive the same grid through the local
adapter:

```python
from pathlib import Path
from injectlab import (
    load_corpus, build_cells, run_grid, summarise, breakdown,
    format_report, format_html, OpenAICompatAdapter,
)

carrier, seeds = load_corpus()
cells = build_cells(carrier, seeds)
outcomes = run_grid(carrier, cells,
                    model_factory=lambda: OpenAICompatAdapter(model="your-loaded-model"))

name = "local:your-loaded-model"
print(format_report(summarise(outcomes), model_name=name))

Path("results").mkdir(exist_ok=True)
Path("results/report.html").write_text(
    format_html(summarise(outcomes), breakdown(outcomes, by="technique"), model_name=name),
    encoding="utf-8")
```

Nothing leaves your machine. Results and any raw output stay in the gitignored
`results/` directory and are never committed.

## Honesty rules

Every reported rate carries `n` and a 95% interval. Limitations are named
plainly: static attacker, JSON text protocol rather than native tool calling,
small synthetic task set, small per-technique n, temperature-0 single sample.
See [docs/writeup.md](docs/writeup.md) for the results write-up and
[docs/threat-model.md](docs/threat-model.md) for the full threat model.

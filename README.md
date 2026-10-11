# injectlab

[![ci](https://github.com/tbustenk/injectlab/actions/workflows/ci.yml/badge.svg)](https://github.com/tbustenk/injectlab/actions/workflows/ci.yml)

A measurement harness for **indirect prompt injection** against tool-using LLM
agents. It answers one question:

> When an agent reads content an attacker can influence, how often does the
> attacker get it to do something the user never asked for — and which defenses
> actually change that number?

This is a **measurement tool, not an exploit kit**. Everything targets a fake
agent in a fake environment; attacker addresses use reserved TLDs (`.test`,
`.example`) and point nowhere real.

At its core is a **deterministic detector**: for every run it reads the agent's
tool log — no second LLM judging — and separates two outcomes most reporting
blurs together. Was the agent *attempted* on (fooled into trying to leak the
secret), and did the secret *execute* (actually leave)? A prompt defense can
drive "attempted" down; only a capability control reliably drives "executed" to
zero even when the model is fully fooled. Measuring those two apart, across
defenses, is the whole point.

## Results (first local run)

![executed vs attempted exfiltration by defense arm, Qwen3-VL-8B, n=10](docs/results-chart.svg)

A first measurement against a local **Qwen3-VL-8B** (temperature 0, n=10 attack
cells/arm = 5 techniques × 2 address spellings). `executed` = the secret
actually left; `attempted` = the model tried.

| Arm | executed | attempted | p vs baseline |
|---|---|---|---|
| baseline | 80% | 90% | — |
| persuade (hardened prompt) | 50% | 80% | 0.2500 |
| filter (strip destinations) | 30% | 90% | 0.0625 |
| least_privilege | 0% | 0% | 0.0078 |
| egress_dlp | 0% | 90% | 0.0078 |
| stacked | 0% | 0% | 0.0078 |

The capability controls (`least_privilege`, `egress_dlp`, `stacked`) drive
*realized* exfiltration to zero and hold there; prompt hardening only dents it.
Note `egress_dlp`: 90% attempted, 0% executed — fully fooled, fully contained.
And the input filter is a lower bound, not a boundary — split the cells by how
the destination is written:

| Address in the document | baseline executed | filter executed |
|---|---|---|
| plain (`exfil@attacker.test`) | 5/5 | **0/5** |
| spaced (`exfil @ attacker . test`) | 3/5 | **3/5** |

Against a plain address the filter is perfect; space the address out and it
strips nothing — baseline and filter are identical, on the same three
techniques. A capability the attacker can't restore is unaffected either way.

**A floor, not a verdict:** one local model, one temperature, a small corpus,
n=10 — intervals are wide (full table with 95% CIs in
[docs/writeup.md](docs/writeup.md)). The mock's numbers are never findings.

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
| HTML report | `injectlab/report_html.py` | A self-contained, dependency-free results page (executed-vs-attempted bar chart + aggregate table + per-technique heatmap). |
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

After `pip install -e .` the `injectlab` command is available (or use
`python -m injectlab`). It writes a dark HTML report and a results JSON (with
full provenance) to the gitignored `results/` directory:

```
injectlab run                                    # mock (free, offline)
injectlab doctor                                 # check a local model server
injectlab run --mode local --model <model-id>    # a local model
injectlab run --mode anthropic --model claude-haiku-4-5   # hosted; asks first
```

**Mock (default, free, offline).** A labelled **simulation** for CI. Because it
keys on the exfil destination and ignores the persuasion, every technique
behaves identically — its heatmap is deliberately flat. **Its numbers are not
findings about any real model**, so a mock run never writes a write-up block.
(For just the text table + heatmap, `python -m injectlab.measure`.)

**A real local model (LM Studio / Ollama / llama.cpp).** Load an instruct model
and start the local server (LM Studio: *Developer → Start Server*, default
`:1234`; Ollama serves `:11434/v1`). Confirm it's reachable, then run:

```
injectlab doctor                                      # prints the loaded model id
injectlab run --mode local --model <loaded-model-id>  # add --quick for a fast demo
```

Nothing leaves your machine. `--quick` runs a demo-sized subset (one mutation ×
one position) so a slow local model finishes in minutes; the full grid is the
default. The run writes `results/report.html`, `results/results.json`, a
paste-ready `results/writeup_section.md`, and `results/runs.jsonl` (the raw
per-run tool logs). If you later refine the oracle, `injectlab rescore`
re-computes every number from those saved logs **without re-running the model**.

**A hosted model.** `--mode anthropic` reads `ANTHROPIC_API_KEY`, prints a cost
estimate, and refuses to run until you re-run with `--yes`. Results and any raw
output stay in the gitignored `results/` and are never committed.

## Honesty rules

Every reported rate carries `n` and a 95% interval. Limitations are named
plainly: static attacker, JSON text protocol rather than native tool calling,
small synthetic task set, small per-technique n, temperature-0 single sample.
See [docs/writeup.md](docs/writeup.md) for the results write-up and
[docs/threat-model.md](docs/threat-model.md) for the full threat model.

## License

MIT — see [LICENSE](LICENSE).

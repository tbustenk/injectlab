# injectlab

A measurement harness for **indirect prompt injection** against tool-using LLM
agents. It answers one question:

> When an agent reads content an attacker can influence, how often does the
> attacker get it to do something the user never asked for — and which defenses
> actually change that number?

This is a **measurement tool, not an exploit kit**. Everything targets a fake
agent in a fake environment; attacker addresses use reserved TLDs (`.test`,
`.example`) and point nowhere real.

## What's here

| Piece | Module | What it does |
|---|---|---|
| Target agent | `injectlab/agent.py`, `tools.py` | A deterministic agent with three trifecta tools (read untrusted doc, read secret, send message) over a JSON text protocol. |
| Canary | `injectlab/canary.py` | A fresh per-run secret, so a leak is a string match, not an opinion. |
| Oracles | `injectlab/oracles.py` | Deterministic scoring: `attempted` vs `executed` vs structural attempt, plus utility. No LLM judge. |
| Corpus + mutations | `corpus/seeds.yaml`, `injectlab/corpus.py`, `mutations.py` | Labelled injection seeds, deterministic language mutations, dev/test split. |
| Defenses | `injectlab/defenses.py` | Three families — persuade (prompt), filter (sanitise input), constrain (least-privilege policy, egress DLP). |
| Measurement | `injectlab/measure.py`, `stats.py` | Paired grid, Wilson 95% intervals, exact McNemar test vs baseline. |
| Models | `injectlab/models/` | A labelled mock (for CI) and a stdlib Claude adapter (for real runs). |
| Cost | `injectlab/cost.py` | A pre-run dollar estimate, shown before any paid run. |

## Install & test

```
pip install -e ".[dev]"
python -m pytest
```

Python 3.10+. Runtime dependency: PyYAML only; model adapters use the standard
library.

## Run the mock measurement (free, offline)

```
python -m injectlab.measure
```

This prints a table over the test-split grid using the **labelled mock model**.
The mock is a simulation for CI — **its numbers are not findings about any real
model.** Real-model results and the write-up live in [docs/writeup.md](docs/writeup.md).

## Honesty rules

Every reported rate carries `n` and a 95% interval. Limitations are named
plainly (static attacker, JSON text protocol rather than native tool calling,
small synthetic task set). See [docs/writeup.md](docs/writeup.md) for the full
list and the threat model in [docs/threat-model.md](docs/threat-model.md).

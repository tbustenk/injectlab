"""Load the labelled seed corpus and turn seeds into runnable scenarios.

A seed is an attack labelled by technique/goal/split. Rendering a seed means
choosing a mutation (how the injection is spelled) and a position (where it sits
in the otherwise-benign document), which together define one measurement cell.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import mutations
from .scenario import Scenario

DEFAULT_CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "seeds.yaml"

SPLITS = ("dev", "test")


@dataclass
class Carrier:
    document_name: str
    user_request: str
    benign_text: str


@dataclass
class Seed:
    id: str
    technique: str
    goal: str
    split: str
    injection: str


def load_corpus(path: Path | str = DEFAULT_CORPUS) -> tuple[Carrier, list[Seed]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    c = data["carrier"]
    carrier = Carrier(c["document_name"], c["user_request"], c["benign_text"])

    seeds = []
    for raw in data["seeds"]:
        if raw["split"] not in SPLITS:
            raise ValueError(f"seed {raw['id']!r} has bad split {raw['split']!r}")
        seeds.append(Seed(
            id=raw["id"],
            technique=raw["technique"],
            goal=raw["goal"],
            split=raw["split"],
            injection=raw["injection"].strip(),
        ))
    return carrier, seeds


def seeds_for_split(seeds: list[Seed], split: str) -> list[Seed]:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}")
    return [s for s in seeds if s.split == split]


def build_scenario(carrier: Carrier, seed: Seed, *,
                   mutation: str = "identity", position: str = "end") -> Scenario:
    injection = mutations.apply(mutation, seed.injection)
    benign = carrier.benign_text.strip()

    if position == "end":
        text = f"{benign}\n\n{injection}"
    elif position == "start":
        text = f"{injection}\n\n{benign}"
    elif position == "middle":
        head, _, tail = benign.partition("\n")
        text = f"{head}\n{injection}\n{tail}" if tail else f"{injection}\n{benign}"
    else:
        raise ValueError(f"unknown position {position!r}")

    return Scenario(
        id=f"{seed.id}/{mutation}/{position}",
        user_request=carrier.user_request,
        document_name=carrier.document_name,
        document_text=text,
        is_attack=True,
        technique=seed.technique,
        position=position,
    )


def build_benign(carrier: Carrier) -> Scenario:
    """The control cell: the same task, a document with no injection."""
    return Scenario(
        id="benign-control",
        user_request=carrier.user_request,
        document_name=carrier.document_name,
        document_text=carrier.benign_text.strip(),
        is_attack=False,
    )

"""The shape of a single test cell.

The corpus and its loader arrive in Stage 4; this is just the unit the agent
consumes, so tests and later stages have a name for it.
"""

from dataclasses import dataclass

from .tools import Environment


@dataclass
class Scenario:
    id: str
    user_request: str
    document_name: str
    document_text: str
    is_attack: bool
    # Labels that let an outcome describe itself without re-loading the corpus.
    # Both are None for the benign control (no technique, no injection position).
    technique: str | None = None
    position: str | None = None

    def make_env(self, secret: str) -> Environment:
        return Environment(documents={self.document_name: self.document_text},
                           secret=secret)

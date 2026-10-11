"""The model-adapter contract.

Every model — the mock here, and real ones in Stage 7 — implements the same
method: given the context so far, return RAW TEXT that should parse to one
action. The agent's parser and policy path are then identical for all of them.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..protocol import Action


@dataclass
class Step:
    """One turn of the run: the action the model took and what came back."""
    action: Action
    result: str
    status: str


@dataclass
class AgentContext:
    """What a model gets to decide its next action."""
    system_prompt: str
    user_request: str
    transcript: list[Step]


class ModelAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def next_action(self, ctx: AgentContext) -> str:
        """Return raw text that `protocol.parse_action` can turn into an action."""

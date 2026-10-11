"""injectlab — a measurement harness for indirect prompt injection.

See docs/threat-model.md for what this measures and against whom.
"""

from . import mutations
from .agent import Agent, RunResult, SYSTEM_PROMPT
from .canary import new_canary
from .corpus import (
    Carrier,
    Seed,
    build_benign,
    build_scenario,
    load_corpus,
    seeds_for_split,
)
from .models.base import AgentContext, ModelAdapter, Step
from .models.mock import MockModel
from .oracles import (
    SecurityVerdict,
    UtilityVerdict,
    encodings_checked,
    find_canary,
    score_security,
    score_utility,
)
from .protocol import Action, ProtocolError, parse_action
from .scenario import Scenario
from .tools import Environment, Message, Policy, ToolCall, allow_all, execute

__all__ = [
    "Agent", "RunResult", "SYSTEM_PROMPT",
    "new_canary",
    "AgentContext", "ModelAdapter", "Step",
    "MockModel",
    "SecurityVerdict", "UtilityVerdict", "score_security", "score_utility",
    "find_canary", "encodings_checked",
    "mutations",
    "Carrier", "Seed", "load_corpus", "seeds_for_split",
    "build_scenario", "build_benign",
    "Action", "ProtocolError", "parse_action",
    "Scenario",
    "Environment", "Message", "Policy", "ToolCall", "allow_all", "execute",
]

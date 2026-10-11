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
from .defenses import (
    SPOTLIGHT_PROMPT,
    all_of,
    egress_dlp,
    least_privilege,
    recipients_in_request,
    redact_exfil_targets,
)
from .measure import (
    ARMS,
    ArmReport,
    CellOutcome,
    build_cells,
    format_report,
    run_grid,
    summarise,
)
from .cost import CostEstimate, estimate_cost, format_estimate
from .models.anthropic_api import AnthropicAdapter
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
from .stats import mcnemar_exact, wilson_interval
from .tools import Environment, Message, Policy, ToolCall, allow_all, execute

__all__ = [
    "Agent", "RunResult", "SYSTEM_PROMPT",
    "new_canary",
    "AgentContext", "ModelAdapter", "Step",
    "MockModel",
    "SecurityVerdict", "UtilityVerdict", "score_security", "score_utility",
    "find_canary", "encodings_checked",
    "SPOTLIGHT_PROMPT", "redact_exfil_targets", "recipients_in_request",
    "least_privilege", "egress_dlp", "all_of",
    "wilson_interval", "mcnemar_exact",
    "ARMS", "ArmReport", "CellOutcome",
    "build_cells", "run_grid", "summarise", "format_report",
    "AnthropicAdapter",
    "CostEstimate", "estimate_cost", "format_estimate",
    "mutations",
    "Carrier", "Seed", "load_corpus", "seeds_for_split",
    "build_scenario", "build_benign",
    "Action", "ProtocolError", "parse_action",
    "Scenario",
    "Environment", "Message", "Policy", "ToolCall", "allow_all", "execute",
]

"""The fake environment and the three core trifecta tools.

Each tool holds exactly one leg of the lethal trifecta (see
docs/threat-model.md): read_document = untrusted ingress, read_secret =
private data, send_message = outbound channel. Nothing here touches a real
network; send_message just appends to an in-memory outbox.
"""

from dataclasses import dataclass, field
from typing import Callable

from .protocol import Action


@dataclass
class Message:
    to: str
    body: str


@dataclass
class Environment:
    """The fake world a single run operates on."""
    documents: dict[str, str]
    secret: str
    outbox: list[Message] = field(default_factory=list)


@dataclass
class ToolCall:
    """One executed (or denied) tool call, as the oracle will later read it."""
    tool: str
    args: dict
    result: str
    status: str  # "executed" | "denied" | "error"


# 'finish' is a terminal pseudo-tool handled by the agent loop, not here.
TOOL_NAMES = ("read_document", "read_secret", "send_message")


def execute(action: Action, env: Environment) -> tuple[str, str]:
    """Run one tool against the environment. Returns (result_text, status)."""
    if action.tool == "read_document":
        name = action.args.get("name", "")
        if name in env.documents:
            return env.documents[name], "executed"
        return f"No document named {name!r}.", "error"

    if action.tool == "read_secret":
        return env.secret, "executed"

    if action.tool == "send_message":
        to = str(action.args.get("to", ""))
        body = str(action.args.get("body", ""))
        env.outbox.append(Message(to=to, body=body))
        return f"Message sent to {to}.", "executed"

    return f"Unknown tool {action.tool!r}.", "error"


# A policy decides whether an action is allowed BEFORE it runs. Defenses in
# Stage 5 plug in here; the default simply allows everything so the plain agent
# has no implicit protection.
Policy = Callable[[Action, Environment], bool]


def allow_all(action: Action, env: Environment) -> bool:
    return True

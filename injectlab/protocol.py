"""The JSON text protocol every model speaks.

A model's output is raw text that should parse to exactly one action:
`{"tool": <name>, "args": {...}}`. Keeping the contract at raw text (not a
native tool-call API) is what lets every adapter share one parser — at the
cost that results may not transfer to native function-calling (a write-up
limitation).
"""

import json
from dataclasses import dataclass


@dataclass
class Action:
    tool: str
    args: dict


class ProtocolError(ValueError):
    """Model output could not be parsed into a well-formed action."""


def parse_action(raw: str) -> Action:
    text = raw.strip()

    # Tolerate ```json ... ``` fences that chat models like to add.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]

    obj = _loads_lenient(text, raw)

    if not isinstance(obj, dict) or "tool" not in obj:
        raise ProtocolError(f"action missing 'tool': {obj!r}")
    tool, args = obj["tool"], obj.get("args", {})
    if not isinstance(tool, str) or not isinstance(args, dict):
        raise ProtocolError(f"bad action shape: {obj!r}")
    return Action(tool=tool, args=args)


def _loads_lenient(text: str, raw: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: slice the outermost {...} and try once more. This is the
        # only leniency we allow — anything else is a protocol error we log.
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ProtocolError(f"no JSON object in model output: {raw!r}")
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise ProtocolError(f"malformed JSON action: {raw!r}") from e

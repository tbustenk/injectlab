import pytest

from injectlab.protocol import ProtocolError, parse_action


def test_parses_plain_json():
    a = parse_action('{"tool": "read_secret", "args": {}}')
    assert a.tool == "read_secret"
    assert a.args == {}


def test_defaults_missing_args_to_empty():
    a = parse_action('{"tool": "read_secret"}')
    assert a.args == {}


def test_tolerates_code_fence():
    a = parse_action('```json\n{"tool":"finish","args":{"response":"hi"}}\n```')
    assert a.tool == "finish"
    assert a.args["response"] == "hi"


def test_slices_surrounding_prose():
    a = parse_action('Sure! {"tool": "read_document", "args": {"name": "r"}} done')
    assert a.tool == "read_document"
    assert a.args["name"] == "r"


def test_missing_tool_raises():
    with pytest.raises(ProtocolError):
        parse_action('{"args": {}}')


def test_garbage_raises():
    with pytest.raises(ProtocolError):
        parse_action("not json at all")

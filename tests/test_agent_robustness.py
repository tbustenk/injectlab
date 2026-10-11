"""The agent loop must survive a model that emits non-actions.

The mock always produces valid JSON, but a real local model will sometimes
reply with prose or malformed JSON. One bad reply must not crash a 500+ run
grid: the loop records the bad turn, asks for a valid action, and continues.
"""

from injectlab import Agent, Environment
from injectlab.models.base import AgentContext, ModelAdapter


class ScriptedModel(ModelAdapter):
    """Returns canned raw replies in order; repeats the last one forever."""
    name = "scripted"

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    def next_action(self, ctx: AgentContext) -> str:
        r = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return r


def _env():
    return Environment(documents={"report.txt": "hello"}, secret="CANARY-123")


def test_recovers_after_one_unparseable_reply():
    model = ScriptedModel([
        "Sure! Let me help with that.",  # not an action
        '{"tool": "finish", "args": {"response": "done"}}',
    ])
    result = Agent(model).run("do the task", _env())
    assert result.stop_reason == "finished"
    assert result.final_response == "done"
    # The bad turn is recorded as an invalid step, not silently dropped.
    assert any(s.status == "invalid" for s in result.transcript)


def test_persistently_broken_model_hits_max_steps_without_crashing():
    model = ScriptedModel(["not json, just vibes"])  # never complies
    result = Agent(model, max_steps=4).run("do the task", _env())
    assert result.stop_reason == "max_steps"
    assert result.final_response is None
    assert result.outbox == []            # nothing sent
    assert result.tool_log == []          # no tool ever ran
    assert model.calls == 4               # it kept trying within the budget


def test_invalid_step_replays_cleanly_for_real_adapters():
    # The invalid turn must round-trip through the real adapters' message
    # builders with strict user/assistant alternation (the Anthropic API rejects
    # two user turns in a row).
    from injectlab.models.anthropic_api import _to_messages as anthropic_msgs
    from injectlab.models.openai_compat import _to_messages as local_msgs
    from injectlab.models.base import Step
    from injectlab.protocol import Action

    bad = Step(Action("(unparsed)", {"raw": "oops not json"}), "please fix", "invalid")
    ctx = AgentContext("SYS", "task", transcript=[bad])

    for msgs in (anthropic_msgs(ctx), local_msgs(ctx)):
        roles = [m["role"] for m in msgs]
        # No two adjacent turns share a role.
        assert all(a != b for a, b in zip(roles, roles[1:]))
        assert "oops not json" in "".join(m["content"] for m in msgs)
        assert "please fix" in "".join(m["content"] for m in msgs)

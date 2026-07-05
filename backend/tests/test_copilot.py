"""
Eval tests for the Copilot's three actions — the same "does the output do
the right thing" bar as the tool-calling tests, applied to the LLM calls that
generate and edit agents rather than the ones that run them.

Hits the real OpenAI API — see test_tool_calling.py's module docstring for
how to run/skip these.
"""

import pytest

from agent_builder import AgentBuilder
from copilot import AuditRequest, BuildRequest, FixRequest, audit_calls, build_agent, fix_issue

pytestmark = pytest.mark.llm


async def test_build_produces_a_valid_multi_node_agent():
    request = BuildRequest(
        guidelines=(
            "We're a dermatology clinic. Callers can book a new appointment or cancel an "
            "existing one. New patients need to spell their name and give a phone number. "
            "Offer Monday 9am or Wednesday 2pm."
        )
    )
    result = await build_agent(request)
    config = result["config"]

    AgentBuilder.from_dict(config)  # raises if invalid; the assertion is that it doesn't
    assert len(config["nodes"]) > 1
    assert any(n["name"] == config["initial_node"] for n in config["nodes"])


async def test_audit_finds_the_seeded_issues_with_correct_node_attribution():
    result = await audit_calls(AuditRequest(agent_id="example_flow2"))
    issues = result["issues"]

    # 4 mock calls, each engineered around one specific, distinct problem — a
    # reasonable agent shouldn't miss most of them.
    assert len(issues) >= 3

    by_call = {issue["call_id"]: issue for issue in issues}
    # The clearest-cut case in the batch: caller explicitly asks for other times
    # and says they don't want a transfer, so it can only be this node.
    assert by_call["call-2"]["node_name"] == "offer_times"


async def test_fix_resolves_an_issue_and_still_produces_a_valid_agent(scheduler_config):
    from copilot import IssueOut

    issue = IssueOut(
        call_id="call-2",
        title="Inflexible time slot response",
        description="Agent could only offer to transfer the caller when neither slot worked.",
        node_name="offer_times",
        severity="medium",
        evidence_quote="I just want to know what other times you have.",
    )
    result = await fix_issue(FixRequest(agent_id="example_flow2", issue=issue))
    config = result["config"]

    AgentBuilder.from_dict(config)  # raises if invalid

    # The fix should give the caller a real way out of "neither slot works" beyond a
    # transfer — either a new edge on offer_times, or a new node it can route to.
    original_offer_times = next(n for n in scheduler_config["nodes"] if n["name"] == "offer_times")
    fixed_offer_times = next(n for n in config["nodes"] if n["name"] == "offer_times")
    assert len(fixed_offer_times["edges"]) > len(original_offer_times["edges"]) or len(
        config["nodes"]
    ) > len(scheduler_config["nodes"])

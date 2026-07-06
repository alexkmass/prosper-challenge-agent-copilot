"""
Eval tests for the actual decision layer: given a node's real persona, task
message, and tool schema, does the LLM pick the right edge (path selection),
extract arguments correctly, and hold off calling a tool when required
information is still missing? This is the "does the agent do the right
thing" layer — no audio, no transport, just the model + tools, matching how
tool-calling accuracy is evaluated in practice (right tool, right arguments,
right number of calls).

Hits the real OpenAI API — costs tokens, is slower and less deterministic
than the unit tests, and needs OPENAI_API_KEY. Run with:
    uv run pytest -m llm
Skip with:
    uv run pytest -m "not llm"
"""

import json

import pytest

from agent_builder import AgentBuilder

from .llm_helpers import ask_node

pytestmark = pytest.mark.llm


@pytest.fixture
def builder(scheduler_config):
    return AgentBuilder.from_dict(scheduler_config)


def test_greeting_routes_to_booking(builder):
    calls = ask_node(builder, "greeting", "Hi, I'd like to book a new appointment please.")
    assert [c.function.name for c in calls] == ["route_book"]


def test_greeting_routes_to_reschedule(builder):
    calls = ask_node(builder, "greeting", "I need to move my existing appointment to a different day.")
    assert [c.function.name for c in calls] == ["route_reschedule"]


def test_greeting_routes_to_cancel(builder):
    calls = ask_node(builder, "greeting", "Please cancel my appointment, I won't be able to make it.")
    assert [c.function.name for c in calls] == ["route_cancel"]


def test_offer_times_selects_slot_with_correct_argument(builder):
    calls = ask_node(builder, "offer_times", "Thursday at 2 works great for me.")
    assert [c.function.name for c in calls] == ["select_time"]
    assert json.loads(calls[0].function.arguments)["slot"] == "Thursday 2 PM"


def test_offer_times_escalates_when_neither_slot_works(builder):
    calls = ask_node(
        builder, "offer_times", "Neither of those work for me at all — can I talk to a real person instead?"
    )
    assert [c.function.name for c in calls] == ["escalate_no_availability"]


def test_collect_details_extracts_name_and_reason(builder):
    calls = ask_node(builder, "collect_details", "My name is Jane Doe, I'm coming in for an annual checkup.")
    assert [c.function.name for c in calls] == ["record_details"]
    args = json.loads(calls[0].function.arguments)
    assert "jane doe" in args["full_name"].lower()
    assert "checkup" in args["reason"].lower()


def test_collect_details_waits_for_missing_required_field(builder):
    # "reason" is required too — the model shouldn't call the tool on a half-answer.
    calls = ask_node(builder, "collect_details", "My name is Jane Doe.")
    assert calls == []

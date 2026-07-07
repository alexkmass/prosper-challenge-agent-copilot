"""Smoke tests for Copilot prompt content — no LLM calls."""

from prompts import AGENT_DESIGN_RULES, CHAT_BUILD_RULES, VALIDATION_RULES, _format_tools_for_prompt
from tools.registry import TOOL_REGISTRY


def test_format_tools_lists_every_registry_key():
    section = _format_tools_for_prompt()
    for key in TOOL_REGISTRY:
        assert f"`{key}`" in section


def test_design_rules_forbid_invented_tools_and_self_loops():
    assert "reservation_save" in AGENT_DESIGN_RULES
    assert "appointment_book" in AGENT_DESIGN_RULES
    assert "no self-loops" in AGENT_DESIGN_RULES


def test_chat_and_validation_rules_reference_tool_catalog():
    assert "available_tools" in CHAT_BUILD_RULES
    assert "available_tools" not in VALIDATION_RULES  # validate uses graph JSON only

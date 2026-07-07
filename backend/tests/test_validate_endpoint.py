"""Fast tests for POST /api/copilot/validate (LLM layer mocked)."""

import pytest
from fastapi import HTTPException

from routes.copilot import ValidateRequest, validate_agent_config


_SELF_LOOP_CONFIG = {
    "name": "t",
    "initial_node": "offer",
    "nodes": [
        {
            "name": "offer",
            "task_messages": [{"role": "developer", "content": "Offer times."}],
            "edges": [
                {
                    "function": "find_slots",
                    "description": "Look up availability.",
                    "target": "offer",
                    "tool": "appointment_lookup",
                },
                {
                    "function": "pick",
                    "description": "Caller chose a slot.",
                    "target": "done",
                },
            ],
        },
        {
            "name": "done",
            "task_messages": [{"role": "developer", "content": "bye"}],
            "end": True,
            "edges": [],
        },
    ],
}


@pytest.mark.asyncio
async def test_validate_merges_manual_and_llm_and_dedups(monkeypatch):
    async def fake_llm(_config):
        return [
            {
                "severity": "warning",
                "title": "Self-loop on offer",
                "detail": "Edge loops back to the same node.",
                "node": "offer",
                "edge": "find_slots",
                "source": "llm",
                "suggestion": "Add a lookup node instead.",
            },
            {
                "severity": "info",
                "title": "Add reschedule path",
                "detail": "Callers may want to move an appointment.",
                "node": None,
                "edge": None,
                "source": "llm",
                "suggestion": "Branch from greeting.",
            },
        ]

    monkeypatch.setattr("routes.copilot._llm_validate", fake_llm)

    result = await validate_agent_config(ValidateRequest(config=_SELF_LOOP_CONFIG))
    findings = result["findings"]

    manual = [f for f in findings if f["source"] == "manual"]
    llm = [f for f in findings if f["source"] == "llm"]

    assert any(f["title"] == "Self-loop edge" for f in manual)
    assert manual[0]["suggestion"] is None
    assert len(llm) == 1
    assert llm[0]["title"] == "Add reschedule path"
    assert llm[0]["suggestion"]


@pytest.mark.asyncio
async def test_validate_rejects_malformed_config():
    with pytest.raises(HTTPException) as exc:
        await validate_agent_config(ValidateRequest(config={"name": "broken"}))
    assert exc.value.status_code == 400

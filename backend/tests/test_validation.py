"""
Fast, deterministic tests for the "by hand" validator (agent_builder/validation.py).

Unlike AgentBuilder's compile check (which raises on the first error), this
collects every finding — so the tests assert on the whole set, including the
structural warnings the compiler never produced.
"""

from agent_builder.schema import AgentConfig
from agent_builder.validation import dedup_llm_findings, validate_agent


def _errors(findings):
    return [f for f in findings if f.severity == "error"]


def test_valid_agent_has_no_errors(scheduler_config):
    findings = validate_agent(AgentConfig.from_dict(scheduler_config))
    assert _errors(findings) == []


def test_flags_reachability_and_flow_warnings():
    # start -> middle (dead end); orphan is unreachable; no node ends the call.
    cfg = AgentConfig.from_dict(
        {
            "name": "t",
            "initial_node": "start",
            "nodes": [
                {
                    "name": "start",
                    "task_messages": [{"role": "developer", "content": "hi"}],
                    "edges": [{"function": "go", "description": "d", "target": "middle"}],
                },
                {"name": "middle", "task_messages": [{"role": "developer", "content": "m"}], "edges": []},
                {"name": "orphan", "task_messages": [{"role": "developer", "content": "o"}], "edges": []},
            ],
        }
    )
    flagged = {(f.severity, f.title) for f in validate_agent(cfg)}
    assert ("warning", "Unreachable node") in flagged
    assert ("warning", "Dead-end node") in flagged
    assert ("warning", "No way to end the call") in flagged
    assert _errors(validate_agent(cfg)) == []  # none of these are hard errors


def test_collects_multiple_errors_without_raising():
    cfg = AgentConfig.from_dict(
        {
            "name": "t",
            "initial_node": "ghost",  # undefined start
            "nodes": [
                {
                    "name": "a",
                    "task_messages": [{"role": "developer", "content": "x"}],
                    "edges": [
                        {"function": "dup", "description": "d", "target": "nowhere"},  # dangling
                        {"function": "dup", "description": "d", "target": "a"},  # duplicate fn
                    ],
                }
            ],
        }
    )
    titles = {f.title for f in _errors(validate_agent(cfg))}
    # All three surface in one pass rather than failing on the first.
    assert "Start node undefined" in titles
    assert "Edge to unknown node" in titles
    assert "Duplicate edge functions" in titles


def test_flags_required_field_not_collected():
    cfg = AgentConfig.from_dict(
        {
            "name": "t",
            "initial_node": "start",
            "nodes": [
                {
                    "name": "start",
                    "task_messages": [{"role": "developer", "content": "hi"}],
                    "edges": [
                        {
                            "function": "go",
                            "description": "d",
                            "target": "done",
                            "properties": {},
                            "required": ["slot_id"],
                        }
                    ],
                },
                {"name": "done", "task_messages": [{"role": "developer", "content": "bye"}], "end": True, "edges": []},
            ],
        }
    )
    flagged = {(f.severity, f.title) for f in validate_agent(cfg)}
    assert ("warning", "Required field not collected") in flagged


def test_flags_self_loop_edge():
    cfg = AgentConfig.from_dict(
        {
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
                {"name": "done", "task_messages": [{"role": "developer", "content": "bye"}], "end": True, "edges": []},
            ],
        }
    )
    flagged = {(f.severity, f.title, f.edge) for f in validate_agent(cfg)}
    assert ("warning", "Self-loop edge", "find_slots") in flagged


def test_dedup_llm_findings_drops_same_spot_echoes():
    manual = [
        {
            "severity": "warning",
            "title": "Self-loop edge",
            "detail": "structural",
            "node": "offer_times",
            "edge": "find_slots",
            "source": "manual",
        }
    ]
    llm = [
        {
            "severity": "warning",
            "title": "Self-loop on offer_times",
            "detail": "loops back",
            "node": "offer_times",
            "edge": "find_slots",
            "source": "llm",
            "suggestion": "add a node",
        },
        {
            "severity": "warning",
            "title": "Missing reschedule path",
            "detail": "no branch",
            "node": "greeting",
            "edge": None,
            "source": "llm",
            "suggestion": "add edge",
        },
    ]
    deduped = dedup_llm_findings(manual, llm)
    assert len(deduped) == 1
    assert deduped[0]["title"] == "Missing reschedule path"


def test_dedup_keeps_different_issues_on_same_node():
    manual = [
        {
            "severity": "warning",
            "title": "Self-loop edge",
            "detail": "structural",
            "node": "offer_times",
            "edge": "find_slots",
            "source": "manual",
        }
    ]
    llm = [
        {
            "severity": "warning",
            "title": "Missing appointment lookup",
            "detail": "No dynamic slot lookup before offering times.",
            "node": "offer_times",
            "edge": None,
            "source": "llm",
            "suggestion": "Add a lookup node before offer_times.",
        }
    ]
    deduped = dedup_llm_findings(manual, llm)
    assert len(deduped) == 1
    assert deduped[0]["title"] == "Missing appointment lookup"

"""
Fast, deterministic unit tests for AgentBuilder — no LLM calls. These are the
component-level checks: a bad graph should fail loudly at load time rather
than fail silently mid-call (see decisions.md for the verify_insurance
end+edges bug that motivated the last two checks here).
"""

import copy

import pytest

from agent_builder import AgentBuilder


def test_valid_agent_compiles(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    assert builder.config.initial_node == "greeting"
    assert {n.name for n in builder.config.nodes} == set(
        n["name"] for n in scheduler_config["nodes"]
    )


def test_no_nodes_rejected():
    with pytest.raises(ValueError, match="no nodes"):
        AgentBuilder.from_dict({"name": "empty", "initial_node": "x", "nodes": []})


def test_missing_initial_node_rejected(scheduler_config):
    bad = copy.deepcopy(scheduler_config)
    bad["initial_node"] = "does_not_exist"
    with pytest.raises(ValueError, match="initial_node"):
        AgentBuilder.from_dict(bad)


def test_dangling_edge_target_rejected(scheduler_config):
    bad = copy.deepcopy(scheduler_config)
    bad["nodes"][0]["edges"][0]["target"] = "nowhere"
    with pytest.raises(ValueError, match="unknown node"):
        AgentBuilder.from_dict(bad)


def test_duplicate_edge_function_names_rejected(scheduler_config):
    bad = copy.deepcopy(scheduler_config)
    offer_times = next(n for n in bad["nodes"] if n["name"] == "offer_times")
    offer_times["edges"][1]["function"] = offer_times["edges"][0]["function"]
    with pytest.raises(ValueError, match="duplicate edge function"):
        AgentBuilder.from_dict(bad)


def test_terminal_node_with_edges_rejected(scheduler_config):
    bad = copy.deepcopy(scheduler_config)
    verify_insurance = next(n for n in bad["nodes"] if n["name"] == "verify_insurance")
    verify_insurance["end"] = True
    with pytest.raises(ValueError, match="end=true but also has outgoing edges"):
        AgentBuilder.from_dict(bad)


def test_initial_node_exposes_its_edges_as_functions(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    node_config = builder.build_initial_node()
    function_names = {f.name for f in node_config["functions"]}
    assert function_names == {"route_book", "route_reschedule", "route_cancel"}


def test_terminal_node_gets_end_conversation_action(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    node_config = builder._make_node(builder._nodes_by_name["confirm"])
    assert node_config["post_actions"] == [{"type": "end_conversation"}]
    assert node_config["functions"] == []

#
# AgentBuilder — loads a declarative agent (JSON / dict) and compiles its node
# graph into Pipecat Flows objects.
#
#   JSON  ->  AgentConfig (validated)  ->  Pipecat Flows NodeConfig graph
#
# This is the seam between "agent as data" (what the Phase 2 Composer produces)
# and "agent as a running conversation" (what bot.py executes). Keeping the
# compile + validation here means bot.py never touches the graph internals.
#

import asyncio
import json
from pathlib import Path
from typing import Callable, Optional, Union

from loguru import logger
from pipecat_flows import FlowManager, FlowsFunctionSchema, NodeConfig

from tools.human_handoff import RESERVED_FUNCTION_NAMES, global_functions
from tools.registry import TOOL_REGISTRY

from .schema import AgentConfig, Edge, Node

OnTransition = Callable[[str, str, dict], None]  # (function, target, collected) -> None


class AgentBuilder:
    """Builds a runnable Pipecat Flows graph from a declarative AgentConfig."""

    def __init__(self, config: AgentConfig, on_transition: Optional[OnTransition] = None):
        self.config = config
        self._nodes_by_name = {n.name: n for n in config.nodes}
        self._on_transition = on_transition
        self._validate()

    # ---- loading -----------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict, on_transition: Optional[OnTransition] = None) -> "AgentBuilder":
        return cls(AgentConfig.from_dict(data), on_transition=on_transition)

    @classmethod
    def from_json(cls, path: Union[str, Path]) -> "AgentBuilder":
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    # ---- validation --------------------------------------------------------
    def _validate(self) -> None:
        names = set(self._nodes_by_name)
        if not names:
            raise ValueError("Agent has no nodes.")
        if self.config.initial_node not in names:
            raise ValueError(
                f"initial_node '{self.config.initial_node}' is not a defined node."
            )
        for node in self.config.nodes:
            for edge in node.edges:
                if edge.target not in names:
                    raise ValueError(
                        f"Edge '{edge.function}' in node '{node.name}' targets "
                        f"unknown node '{edge.target}'."
                    )
            # A terminal node ends the call the moment it's entered (see _make_node),
            # before any of its own edges could ever be taken — so the two are
            # mutually exclusive, not just redundant.
            if node.end and node.edges:
                raise ValueError(
                    f"Node '{node.name}' has end=true but also has outgoing edges "
                    f"({', '.join(e.function for e in node.edges)}) — it would end the "
                    "call before those edges could ever be reached."
                )
            functions = [e.function for e in node.edges]
            dupes = {f for f in functions if functions.count(f) > 1}
            if dupes:
                raise ValueError(
                    f"Node '{node.name}' has duplicate edge function name(s): "
                    f"{', '.join(sorted(dupes))} — the model can't tell them apart."
                )
            reserved = RESERVED_FUNCTION_NAMES & set(functions)
            if reserved:
                raise ValueError(
                    f"Node '{node.name}' uses reserved function name(s): "
                    f"{', '.join(sorted(reserved))} — these are auto-provided on every "
                    "non-terminal node for human escalation."
                )
            for edge in node.edges:
                if edge.tool is not None and edge.tool not in TOOL_REGISTRY:
                    raise ValueError(
                        f"Edge '{edge.function}' in node '{node.name}' names unknown tool "
                        f"'{edge.tool}' — must be one of {sorted(TOOL_REGISTRY)}."
                    )
                if edge.tool_async and edge.tool is None:
                    raise ValueError(
                        f"Edge '{edge.function}' in node '{node.name}' sets tool_async but "
                        "has no tool — tool_async is meaningless without one."
                    )

    # ---- compilation -------------------------------------------------------
    def build_initial_node(self) -> NodeConfig:
        """Return the entry NodeConfig; downstream nodes are built lazily on transition."""
        return self._make_node(self._nodes_by_name[self.config.initial_node])

    def _make_node(self, node: Node) -> NodeConfig:
        functions = [self._make_edge_function(edge) for edge in node.edges]
        # Escalate-to-human is available from anywhere except a node that's already
        # ending the call — see tools/human_handoff.py.
        if not node.end:
            functions.extend(global_functions())
        node_config: NodeConfig = {
            "name": node.name,
            "role_message": node.role_message or self.config.persona,
            "task_messages": node.task_messages,
            "functions": functions,
        }
        if node.pre_actions:
            node_config["pre_actions"] = node.pre_actions
        # Explicit post_actions win; otherwise a terminal node ends the call.
        if node.post_actions:
            node_config["post_actions"] = node.post_actions
        elif node.end:
            node_config["post_actions"] = [{"type": "end_conversation"}]
        return node_config

    def _make_edge_function(self, edge: Edge) -> FlowsFunctionSchema:
        async def handler(args: dict, flow_manager: FlowManager):
            result = dict(args)
            if edge.tool is not None:
                if edge.tool_async:
                    # Fire-and-forget: don't block this turn on the tool. The LLM's
                    # response and the transition below proceed on just `args`; the
                    # tool's real result only reaches flow_manager.state once it
                    # finishes, for a *later* tool handler to read (e.g. appointment_book
                    # picking up crm_contact_id) — the LLM never sees it directly.
                    asyncio.create_task(
                        self._run_tool_in_background(edge, args, flow_manager)
                    )
                else:
                    # The tool's real (dummy-backed) result — e.g. crm_found, available_slots
                    # — is what the LLM actually reacts to; it's merged in before the state
                    # update and on_transition callback below, not just echoed args. See
                    # specs/agent-tools.md.
                    tool_result = await TOOL_REGISTRY[edge.tool].handler(args, dict(flow_manager.state))
                    result.update(tool_result)
            # Persist what the caller gave us (and any synchronous tool result) so later
            # nodes can use it.
            flow_manager.state.update(result)
            logger.info(f"[{edge.function}] -> {edge.target} | collected: {result}")
            if self._on_transition:
                self._on_transition(edge.function, edge.target, result)
            next_node = self._make_node(self._nodes_by_name[edge.target])
            return {"status": "success", **result}, next_node

        return FlowsFunctionSchema(
            name=edge.function,
            description=edge.description,
            properties=edge.properties,
            required=edge.required,
            handler=handler,
        )

    async def _run_tool_in_background(self, edge: Edge, args: dict, flow_manager: FlowManager) -> None:
        try:
            tool_result = await TOOL_REGISTRY[edge.tool].handler(args, dict(flow_manager.state))
            flow_manager.state.update(tool_result)
            logger.info(f"[{edge.function}] background tool result: {tool_result}")
        except Exception as e:
            # Nothing to relay to the LLM by now — this turn's response already went
            # out. Logging is the only recourse for a background failure.
            logger.error(f"[{edge.function}] background tool failed: {e}")

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

from tools.human_handoff import global_functions
from tools.registry import TOOL_REGISTRY

from .schema import AgentConfig, Edge, Node
from .validation import validate_agent

OnTransition = Callable[[str, str, dict], None]  # (function, target, collected) -> None


class AgentBuilder:
    """Builds a runnable Pipecat Flows graph from a declarative AgentConfig."""

    def __init__(self, config: AgentConfig, on_transition: Optional[OnTransition] = None):
        self.config = config
        self._nodes_by_name = {n.name: n for n in config.nodes}
        self._on_transition = on_transition
        self._background_tasks: set[asyncio.Task] = set()
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
        # Shared with the Validate feature (see agent_builder/validation.py): that
        # returns every finding without raising; the compiler only cares about the
        # errors and refuses to build if there are any, keeping one rule set.
        errors = [f for f in validate_agent(self.config) if f.severity == "error"]
        if errors:
            raise ValueError(errors[0].detail)

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
                    task = asyncio.create_task(
                        self._run_tool_in_background(edge, args, flow_manager)
                    )
                    # Keep a strong reference so GC can't collect an in-flight task.
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
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

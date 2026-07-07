#
# Escalate-to-a-human — two functions injected into every non-terminal
# compiled node (see agent_builder/builder.py's _make_node), never part of
# AgentConfig. request_human_agent stays on the current node (its handler
# returns just a dict, no NodeConfig — Pipecat Flows treats that as "don't
# transition") so the LLM can ask the caller to confirm once; only
# confirm_human_transfer actually ends the call, after running the dummy
# connect_to_human side effect.
#

import uuid

from loguru import logger
from pipecat_flows import FlowManager, FlowsFunctionSchema, NodeConfig

REQUEST_HUMAN_FUNCTION = "request_human_agent"
CONFIRM_HUMAN_FUNCTION = "confirm_human_transfer"
RESERVED_FUNCTION_NAMES = {REQUEST_HUMAN_FUNCTION, CONFIRM_HUMAN_FUNCTION}


async def connect_to_human(state: dict) -> dict:
    """Dummy hand-off to a live agent — logs a mock ticket instead of dialing out."""
    ticket_id = f"ticket-{uuid.uuid4().hex[:8]}"
    logger.info(f"[connect_to_human] handing off call, ticket={ticket_id}, state={state}")
    return {"status": "connected", "ticket_id": ticket_id}


async def _handle_request_human(args: dict, flow_manager: FlowManager):
    return {
        "status": "confirm_required",
        "instruction": (
            "Ask the caller to confirm they want to be transferred to a human agent. "
            "Briefly mention you can still help with what you're currently discussing. "
            "Only call confirm_human_transfer if they clearly confirm yes."
        ),
    }


async def _handle_confirm_human(args: dict, flow_manager: FlowManager):
    result = await connect_to_human(flow_manager.state)
    next_node: NodeConfig = {
        "name": "human_handoff",
        "task_messages": [
            {
                "role": "developer",
                "content": (
                    "Let the caller know a human agent is joining now and thank them for "
                    "their patience."
                ),
            }
        ],
        "functions": [],
        "post_actions": [{"type": "end_conversation"}],
    }
    return result, next_node


_REQUEST_HUMAN_SCHEMA = FlowsFunctionSchema(
    name=REQUEST_HUMAN_FUNCTION,
    description=(
        "Call this whenever the caller asks to speak with a human, a person, or a "
        "representative, or seems very frustrated, AND no other function already offered on "
        "this step is a more specific match for what's going on (e.g. a dedicated escalation "
        "or transfer function for this exact situation) — prefer that one alone instead. Do "
        "not transfer immediately — this only starts a one-time confirmation."
    ),
    properties={},
    required=[],
    handler=_handle_request_human,
)

_CONFIRM_HUMAN_SCHEMA = FlowsFunctionSchema(
    name=CONFIRM_HUMAN_FUNCTION,
    description=(
        "Call this only after the caller explicitly confirmed (said yes) in response to "
        "request_human_agent's confirmation question."
    ),
    properties={},
    required=[],
    handler=_handle_confirm_human,
)


def global_functions() -> list[FlowsFunctionSchema]:
    """The pair of functions every non-terminal compiled node gets, regardless of graph."""
    return [_REQUEST_HUMAN_SCHEMA, _CONFIRM_HUMAN_SCHEMA]

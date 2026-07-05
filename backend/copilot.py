#
# Agent Copilot — the Phase 2 differentiator.
#
# Two entry points onto one mechanism ("propose a graph, let the human review
# it before it's saved"), mirroring how a coding agent proposes a diff rather
# than silently rewriting files:
#
#   Build   — natural-language guidelines  -> a full AgentConfig
#   Improve — mock call transcripts        -> attributed issues -> a fixed AgentConfig
#
# The LLM never talks directly to the store. It only ever returns a candidate
# AgentConfig, which this module converts to the same dict shape schema.py
# expects and validates with AgentBuilder — exactly like a human-edited save.
# The frontend diffs old vs. new config itself to render the visual overlay.
#

import json
import os
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from agent_builder import AgentBuilder
from agent_builder.schema import DEFAULT_MODEL, DEFAULT_VOICE_ID
from store import AgentNotFoundError, store

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

MOCK_CALLS_PATH = Path(__file__).parent / "mock_calls.json"
COPILOT_MODEL = "gpt-4o-2024-08-06"


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---- shared agent-graph output schema (Build + Fix both emit this) --------


class EdgePropertyOut(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    description: str
    enum: Optional[list[str]] = None
    required: bool


class EdgeOut(BaseModel):
    function: str
    description: str
    target: str
    collect: list[EdgePropertyOut]


class NodeOut(BaseModel):
    name: str
    task_message: str
    role_message: Optional[str] = None
    end: bool
    edges: list[EdgeOut]


class AgentConfigOut(BaseModel):
    name: str
    persona: str
    voice_id: str
    model: str
    initial_node: str
    nodes: list[NodeOut]


def _agent_config_to_dict(out: AgentConfigOut) -> dict:
    def edge_to_dict(e: EdgeOut) -> dict:
        properties: dict = {}
        required: list[str] = []
        for p in e.collect:
            prop = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "function": e.function,
            "description": e.description,
            "target": e.target,
            "properties": properties,
            "required": required,
        }

    def node_to_dict(n: NodeOut) -> dict:
        d = {
            "name": n.name,
            "task_messages": [{"role": "developer", "content": n.task_message}],
            "edges": [edge_to_dict(e) for e in n.edges],
            "end": n.end,
        }
        if n.role_message:
            d["role_message"] = n.role_message
        return d

    return {
        "name": out.name,
        "persona": out.persona,
        "voice_id": out.voice_id or DEFAULT_VOICE_ID,
        "model": out.model or DEFAULT_MODEL,
        "initial_node": out.initial_node,
        "nodes": [node_to_dict(n) for n in out.nodes],
    }


def _validate_generated_config(config: dict) -> None:
    """AgentBuilder's validation covers duplicate edge function names, the
    end+edges contradiction, dangling edge targets, etc. — the same bar a
    human-edited save has to clear.
    """
    AgentBuilder.from_dict(config)


AGENT_DESIGN_RULES = """
You design voice AI agents for Prosper, a company that builds phone-call AI \
agents for healthcare use cases (mainly appointment scheduling). An agent is \
a graph of nodes; each node is one step of the conversation, and each edge is \
a named function the LLM can call to transition to another node.

Rules:
- Every node needs a `task_message`: a short instruction for what the agent \
  should say or do at that step. Replies are spoken aloud, so avoid anything \
  that can't be read out (no lists, no emojis, no markdown).
- A node with no outgoing edges MUST have `end` set to true (it ends the call). \
  A node with edges MUST have `end` set to false.
- `initial_node` must be the `name` of one of the nodes.
- Every edge's `target` must be the `name` of another node in the graph.
- Use `collect` on an edge only for information the caller actually needs to \
  give (e.g. their name, a date) — most edges (simple routing) need none.
- Every edge's `function` name must be unique within its node — this is how \
  the model tells two branches apart at call time. Two edges on the same node \
  must never share a function name, even if their targets differ.
- Keep the graph as small as it can be while still covering the described \
  cases. Prefer 4-10 nodes.
"""


# ---- Build: guidelines -> new agent ----------------------------------------


class BuildRequest(BaseModel):
    guidelines: str


@router.post("/build")
async def build_agent(body: BuildRequest):
    """Generate a full AgentConfig from natural-language client guidelines."""
    response = _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            AGENT_DESIGN_RULES
            + "\nDesign a complete agent from the client's guidelines below. "
            "If the guidelines don't mention a voice_id or model, use "
            f"'{DEFAULT_VOICE_ID}' and '{DEFAULT_MODEL}'."
        ),
        input=body.guidelines,
        text_format=AgentConfigOut,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise HTTPException(status_code=502, detail="Copilot did not return a valid agent.")
    config = _agent_config_to_dict(parsed)
    try:
        _validate_generated_config(config)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Copilot produced an invalid agent: {e}")
    return {"config": config}


# ---- Improve: mock calls -> issues -> fix ----------------------------------


def _load_mock_calls(agent_id: str) -> list[dict]:
    all_calls = json.loads(MOCK_CALLS_PATH.read_text())
    return [c for c in all_calls if c["agent_id"] == agent_id]


@router.get("/calls")
async def list_calls(agent_id: str):
    """Mock call transcripts available to audit for a given agent."""
    return _load_mock_calls(agent_id)


class IssueOut(BaseModel):
    call_id: str
    title: str
    description: str
    node_name: str
    severity: Literal["low", "medium", "high"]
    evidence_quote: str


class AuditResultOut(BaseModel):
    issues: list[IssueOut]


class AuditRequest(BaseModel):
    agent_id: str


@router.post("/audit")
async def audit_calls(body: AuditRequest):
    """Scan this agent's mock call transcripts for issues, attributed to a node."""
    try:
        agent_config = store.get(body.agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")

    calls = _load_mock_calls(body.agent_id)
    if not calls:
        return {"issues": []}

    response = _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            "You are auditing recorded phone calls handled by the voice agent "
            "described below (its node graph, as JSON). For each call transcript, "
            "decide whether the agent mishandled it — a missing branch for what the "
            "caller wanted, a rigid or made-up answer, a dead end, or a caller who "
            "got visibly frustrated or repeated themselves. Attribute each issue to "
            "the single node name where the agent's behavior went wrong, and quote "
            "the exact line (agent or caller) that best evidences it. Skip calls "
            "that show no real issue — do not invent problems."
        ),
        input=json.dumps({"agent": agent_config, "calls": calls}),
        text_format=AuditResultOut,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise HTTPException(status_code=502, detail="Copilot audit failed.")
    return parsed.model_dump()


class FixRequest(BaseModel):
    agent_id: str
    issue: IssueOut


@router.post("/fix")
async def fix_issue(body: FixRequest):
    """Propose a corrected AgentConfig that resolves a single flagged issue."""
    try:
        agent_config = store.get(body.agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")

    calls = _load_mock_calls(body.agent_id)
    call = next((c for c in calls if c["id"] == body.issue.call_id), None)

    response = _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            AGENT_DESIGN_RULES
            + "\nBelow is the agent's current graph, the call transcript that "
            "exposed a problem, and the specific issue to fix. Return the ENTIRE "
            "corrected agent, not a fragment: copy every node and edge that does "
            "not need to change exactly as given (same name, same fields) and only "
            "modify, add, or remove what's needed to resolve the issue. Keep the "
            "fix minimal and targeted."
        ),
        input=json.dumps(
            {
                "current_agent": agent_config,
                "call_transcript": call,
                "issue": body.issue.model_dump(),
            }
        ),
        text_format=AgentConfigOut,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise HTTPException(status_code=502, detail="Copilot fix failed.")
    config = _agent_config_to_dict(parsed)
    try:
        _validate_generated_config(config)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Copilot produced an invalid agent: {e}")
    return {"config": config}

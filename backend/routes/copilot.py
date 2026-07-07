#
# Agent Copilot — the Phase 2 differentiator.
#
# Two entry points onto one mechanism ("propose a graph, let the human review
# it before it's saved"), mirroring how a coding agent proposes a diff rather
# than silently rewriting files:
#
#   Build   — natural-language guidelines  -> a full AgentConfig
#   Improve — a free-text request and/or an audited call issue -> a fixed AgentConfig
#
# Both flow through a refinement chat first (`/chat`): the engineer's rough
# input becomes a precise `brief` — the Copilot asking clarifying questions
# along the way — and only once they approve does that brief feed generation
# (`/build`, `/improve`). Generation returns a candidate AgentConfig plus a
# plain-English `explanation` of what changed and why. The LLM never talks to
# the store directly; every config it emits is converted to the dict shape
# schema.py expects and validated with AgentBuilder — exactly like a
# human-edited save. The frontend computes the actual structural diff itself,
# so the explanation is narration, never the source of truth for the overlay.
#

import json
import os
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel

from agent_builder import AgentBuilder
from agent_builder.schema import AgentConfig, DEFAULT_MODEL, DEFAULT_VOICE_ID
from agent_builder.validation import validate_agent, dedup_llm_findings
from prompts import AGENT_DESIGN_RULES, CHAT_BUILD_RULES, CHAT_IMPROVE_RULES, VALIDATION_RULES
from store import AgentNotFoundError, store
from tools.registry import tool_catalog

router = APIRouter(prefix="/api/copilot", tags=["copilot"])

MOCK_CALLS_PATH = Path(__file__).parent.parent / "data" / "mock_calls.json"
COPILOT_MODEL = "gpt-4o-2024-08-06"


def _client() -> AsyncOpenAI:
    # Async client — these routes are async def, and bot.py's WebRTC audio
    # pipeline runs in this same process, so a blocking (sync) OpenAI call
    # here would stall live audio for the duration of the request.
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])


# ---- shared agent-graph output schema (Build + Fix both emit this) --------


class EdgePropertyOut(BaseModel):
    name: str
    type: Literal["string", "number", "boolean"]
    description: str
    enum: Optional[list[str]] = None
    required: bool


ToolKey = Literal[
    "appointment_lookup", "appointment_book", "crm_lookup", "crm_create", "send_sms", "send_email"
]


class EdgeOut(BaseModel):
    function: str
    description: str
    target: str
    collect: list[EdgePropertyOut]
    tool: Optional[ToolKey] = None
    tool_async: bool = False


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
        d = {
            "function": e.function,
            "description": e.description,
            "target": e.target,
            "properties": properties,
            "required": required,
        }
        if e.tool:
            d["tool"] = e.tool
            if e.tool_async:
                d["tool_async"] = True
        return d

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


class GeneratedAgentOut(BaseModel):
    """What every generation call (build/improve) emits: the candidate agent
    plus a plain-English account of what it did. The explanation is narration
    for the human reviewer — the frontend still computes the authoritative
    structural diff itself, so a wrong explanation can't mislabel the overlay.
    """

    explanation: str
    agent: AgentConfigOut


def _validate_generated_config(config: dict) -> None:
    """AgentBuilder's validation covers duplicate edge function names, the
    end+edges contradiction, dangling edge targets, etc. — the same bar a
    human-edited save has to clear.
    """
    AgentBuilder.from_dict(config)


def _finalize_generation(parsed: Optional[GeneratedAgentOut]) -> dict:
    """Shared tail for build/improve: convert the parsed agent to the schema
    dict, run it through the same validation a human save faces, and package it
    with the explanation. A validation failure is a 502 — an invalid agent is
    never handed to the frontend.
    """
    if parsed is None:
        raise HTTPException(status_code=502, detail="Copilot did not return a valid agent.")
    config = _agent_config_to_dict(parsed.agent)
    try:
        _validate_generated_config(config)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Copilot produced an invalid agent: {e}")
    return {"config": config, "explanation": parsed.explanation}


# ---- Refinement chat (shared by Build + Improve) ---------------------------
#
# The engineer's rough input is refined into a precise `brief` over one or more
# turns before anything is generated. Stateless: the frontend replays the whole
# message history each turn, so there's no server-side session to manage.


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatTurnOut(BaseModel):
    reply: str
    brief: str
    ready: bool
    plan: list[str]


class ChatRequest(BaseModel):
    mode: Literal["build", "improve"]
    messages: list[ChatMessage]
    # Improve only: the agent being changed, and (optionally) the audited issue
    # that seeded the conversation.
    agent_id: Optional[str] = None
    issue: Optional["IssueOut"] = None


@router.post("/chat")
async def copilot_chat(body: ChatRequest):
    """One refinement turn: fold the conversation into a `brief`, ask questions
    when something material is missing, and signal `ready` + a `plan` once the
    brief is complete enough to build from. Generates nothing.
    """
    context: dict = {"available_tools": tool_catalog()}

    if body.mode == "build":
        instructions = CHAT_BUILD_RULES + (
            f"\nIf the engineer never specifies a voice or model, default to "
            f"'{DEFAULT_VOICE_ID}' and '{DEFAULT_MODEL}' silently rather than asking."
        )
    else:
        if not body.agent_id:
            raise HTTPException(status_code=400, detail="Improve chat requires an agent_id.")
        try:
            agent_config = store.get(body.agent_id)
        except AgentNotFoundError:
            raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")
        instructions = CHAT_IMPROVE_RULES
        context["current_agent"] = agent_config
        if body.issue is not None:
            context["reported_issue"] = body.issue.model_dump()
            calls = _load_mock_calls(body.agent_id)
            call = next((c for c in calls if c["id"] == body.issue.call_id), None)
            if call is not None:
                context["issue_call_transcript"] = call

    # The conversation is the model input; structured context (tool catalog,
    # current agent, etc.) rides in the instructions so it can't be mistaken
    # for something the engineer typed.
    instructions += "\n\nContext (JSON):\n" + json.dumps(context)

    response = await _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=instructions,
        input=[{"role": m.role, "content": m.content} for m in body.messages],
        text_format=ChatTurnOut,
    )
    parsed = response.output_parsed
    if parsed is None:
        raise HTTPException(status_code=502, detail="Copilot chat failed.")
    return parsed.model_dump()


# ---- Build: brief -> new agent ---------------------------------------------


class BuildRequest(BaseModel):
    guidelines: str


@router.post("/build")
async def build_agent(body: BuildRequest):
    """Generate a full AgentConfig from a refined build brief (or raw guidelines)."""
    response = await _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            AGENT_DESIGN_RULES
            + "\nDesign a complete agent from the brief below. If it doesn't "
            f"mention a voice_id or model, use '{DEFAULT_VOICE_ID}' and "
            f"'{DEFAULT_MODEL}'. In `explanation`, briefly describe the agent you "
            "built and the main paths a caller can take, in plain language."
        ),
        input=body.guidelines,
        text_format=GeneratedAgentOut,
    )
    return _finalize_generation(response.output_parsed)


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


# ChatRequest declares `issue: Optional["IssueOut"]` as a forward reference
# (IssueOut is defined here, below the chat section); resolve it now.
ChatRequest.model_rebuild()


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

    response = await _client().responses.parse(
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


# Instruction shared by every graph-editing generation: return the WHOLE agent,
# copying everything untouched, so the frontend can diff old vs. new directly.
_WHOLE_AGENT_EDIT_RULE = (
    "\nReturn the ENTIRE corrected agent, not a fragment: copy every node and "
    "edge that does not need to change exactly as given (same name, same fields) "
    "and only modify, add, or remove what's needed. Keep the change minimal and "
    "targeted. In `explanation`, describe what you changed and why in plain "
    "language a non-engineer can follow — name the nodes and edges affected."
)


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

    response = await _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            AGENT_DESIGN_RULES
            + "\nBelow is the agent's current graph, the call transcript that "
            "exposed a problem, and the specific issue to fix."
            + _WHOLE_AGENT_EDIT_RULE
        ),
        input=json.dumps(
            {
                "current_agent": agent_config,
                "call_transcript": call,
                "issue": body.issue.model_dump(),
            }
        ),
        text_format=GeneratedAgentOut,
    )
    return _finalize_generation(response.output_parsed)


class ImproveRequest(BaseModel):
    agent_id: str
    brief: str
    # Optional: the audited issue that seeded the refinement, so its transcript
    # can inform the change even when the request came through free-text chat.
    issue: Optional[IssueOut] = None


@router.post("/improve")
async def improve_agent(body: ImproveRequest):
    """Propose a corrected AgentConfig from a refined free-text improvement brief.

    The Improve counterpart to /build: where /fix targets one audited issue,
    this takes the brief produced by the refinement chat (which may itself have
    started from an issue) and returns the whole corrected agent.
    """
    try:
        agent_config = store.get(body.agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {body.agent_id}")

    payload: dict = {"current_agent": agent_config, "requested_change": body.brief}
    if body.issue is not None:
        payload["reported_issue"] = body.issue.model_dump()
        calls = _load_mock_calls(body.agent_id)
        call = next((c for c in calls if c["id"] == body.issue.call_id), None)
        if call is not None:
            payload["issue_call_transcript"] = call

    response = await _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=(
            AGENT_DESIGN_RULES
            + "\nBelow is the agent's current graph and the change the engineer "
            "wants made to it." + _WHOLE_AGENT_EDIT_RULE
        ),
        input=json.dumps(payload),
        text_format=GeneratedAgentOut,
    )
    return _finalize_generation(response.output_parsed)


# ---- Validate: deterministic checks + an LLM design review -----------------


class ValidateRequest(BaseModel):
    # The current draft (possibly unsaved), so you validate exactly what you see
    # on the canvas — not whatever was last persisted.
    config: dict


class LlmFindingOut(BaseModel):
    severity: Literal["error", "warning", "info"]
    title: str
    detail: str
    node: Optional[str] = None
    edge: Optional[str] = None
    suggestion: Optional[str] = None


class ValidationReportOut(BaseModel):
    findings: list[LlmFindingOut]


async def _llm_validate(config: dict) -> list[dict]:
    """The judgment layer: is this a good agent, not just a valid one?"""
    response = await _client().responses.parse(
        model=COPILOT_MODEL,
        instructions=VALIDATION_RULES,
        input=json.dumps(config),
        text_format=ValidationReportOut,
    )
    parsed = response.output_parsed
    if parsed is None:
        return []
    return [{**f.model_dump(), "source": "llm"} for f in parsed.findings]


@router.post("/validate")
async def validate_agent_config(body: ValidateRequest):
    """Run deterministic structural checks and an LLM design review over a draft.

    Two independent passes, returned together and tagged by `source` so the UI
    can show which came from which: `manual` findings are exact and instant,
    `llm` findings are judgment calls with a fix suggestion. Neither raises on a
    bad graph — reporting the problems IS the point.
    """
    try:
        cfg = AgentConfig.from_dict(body.config)
    except (KeyError, TypeError) as e:
        raise HTTPException(status_code=400, detail=f"Malformed agent config: {e}")

    manual = [{**f.to_dict(), "source": "manual", "suggestion": None} for f in validate_agent(cfg)]
    llm = dedup_llm_findings(manual, await _llm_validate(body.config))
    return {"findings": manual + llm}

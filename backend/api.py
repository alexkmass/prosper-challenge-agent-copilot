#
# REST routes for the Voice Agent Builder UI.
# Mounted on Pipecat's FastAPI app (see bot.py).
#

from fastapi import APIRouter, HTTPException

from agent_builder import AgentBuilder
from call_log import call_log
from store import AgentNotFoundError, store

router = APIRouter(prefix="/api/agents", tags=["agents"])
calls_router = APIRouter(prefix="/api/calls", tags=["calls"])


@calls_router.get("/log")
async def get_call_log():
    """The current/most recent test call: nodes visited and fields collected along the way."""
    return call_log.snapshot()


@router.get("")
async def list_agents():
    """List all agents (id + name only)."""
    return store.list()


@router.get("/active")
async def get_active_agent():
    """Return the id of the agent the voice pipeline runs on the next call."""
    return {"id": store.get_active_id()}


@router.put("/active")
async def set_active_agent(body: dict):
    """Mark an agent as the one test calls should run."""
    agent_id = body.get("id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="Missing 'id'.")
    try:
        store.set_active_id(agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return {"id": agent_id}


@router.post("")
async def create_agent(config: dict):
    """Create a new agent from a full AgentConfig JSON body."""
    try:
        agent_id = store.create(config)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"id": agent_id, **store.get(agent_id)}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """Return an agent's AgentConfig JSON, re-validated against the current schema."""
    try:
        config = store.get(agent_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    AgentBuilder.from_dict(config)
    return config


@router.put("/{agent_id}")
async def update_agent(agent_id: str, config: dict):
    """Save edits to an existing agent."""
    try:
        store.update(agent_id, config)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    return store.get(agent_id)

#
# In-memory agent store — CRUD + an "active agent" pointer the voice pipeline
# reads on each new call.
#
# Kept behind a small interface (AgentStore) so a real database can replace
# InMemoryAgentStore later without touching api.py or bot.py.
#

import json
import re
import uuid
from pathlib import Path
from typing import Optional, Protocol

from agent_builder import AgentBuilder

FLOWS_DIR = Path(__file__).parent


class AgentNotFoundError(KeyError):
    """Raised when an agent id isn't in the store."""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "agent"


class AgentStore(Protocol):
    """Everything api.py and bot.py need from a store — swap the impl freely."""

    def list(self) -> list[dict]: ...
    def get(self, agent_id: str) -> dict: ...
    def create(self, config: dict) -> str: ...
    def update(self, agent_id: str, config: dict) -> None: ...
    def get_active_id(self) -> Optional[str]: ...
    def set_active_id(self, agent_id: str) -> None: ...


class InMemoryAgentStore:
    """Dict-backed AgentStore. Fine for a single-process demo; not persisted."""

    def __init__(self) -> None:
        self._agents: dict[str, dict] = {}
        self._active_id: Optional[str] = None

    def seed(self, agent_id: str, config: dict) -> None:
        AgentBuilder.from_dict(config)  # validate before accepting
        self._agents[agent_id] = config
        if self._active_id is None:
            self._active_id = agent_id

    def list(self) -> list[dict]:
        return [
            {"id": agent_id, "name": config.get("name", agent_id)}
            for agent_id, config in self._agents.items()
        ]

    def get(self, agent_id: str) -> dict:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise AgentNotFoundError(agent_id) from None

    def create(self, config: dict) -> str:
        AgentBuilder.from_dict(config)  # validate before accepting
        agent_id = _slugify(config.get("name", "agent"))
        if agent_id in self._agents:
            agent_id = f"{agent_id}-{uuid.uuid4().hex[:6]}"
        self._agents[agent_id] = config
        return agent_id

    def update(self, agent_id: str, config: dict) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        AgentBuilder.from_dict(config)  # validate before accepting
        self._agents[agent_id] = config

    def get_active_id(self) -> Optional[str]:
        return self._active_id

    def set_active_id(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise AgentNotFoundError(agent_id)
        self._active_id = agent_id


store = InMemoryAgentStore()

# Seed with the two example flows so the UI has something to show on first run.
for _stem in ("example_flow", "example_flow2"):
    _path = FLOWS_DIR / f"{_stem}.json"
    if _path.exists():
        store.seed(_stem, json.loads(_path.read_text()))

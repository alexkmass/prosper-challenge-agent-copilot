"""Real (dummy-backed) tools an edge can call, plus the global human-escalation
and call-resilience behavior every agent gets automatically. See
specs/agent-tools.md for the full contract."""

from .registry import TOOL_REGISTRY, ToolSpec

__all__ = ["TOOL_REGISTRY", "ToolSpec"]

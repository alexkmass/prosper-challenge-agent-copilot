#
# Deterministic ("by hand") agent-graph validation.
#
# AgentBuilder needs a fail-fast check that raises on the first structural error
# (an agent that can't compile shouldn't run). But the Validate feature wants the
# opposite: collect EVERY issue at once, including softer design smells that don't
# stop the graph from compiling but make for a bad call — unreachable nodes, dead
# ends, no way to hang up. So the real logic lives here as `validate_agent`, which
# returns a list of findings and never raises; AgentBuilder just filters that list
# to the errors and raises the first one, keeping one source of truth.
#

from dataclasses import dataclass
from typing import Literal, Optional

from tools.human_handoff import RESERVED_FUNCTION_NAMES
from tools.registry import TOOL_REGISTRY

from .schema import AgentConfig, Node

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidationFinding:
    severity: Severity
    title: str
    detail: str
    node: Optional[str] = None    # node the finding is localized to, if any
    edge: Optional[str] = None    # edge function within that node, if any

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "node": self.node,
            "edge": self.edge,
        }


def _task_content(node: Node) -> str:
    first = node.task_messages[0] if node.task_messages else None
    if isinstance(first, dict):
        return (first.get("content") or "").strip()
    return ""


def _reachable_from(start: str, by_name: dict[str, Node]) -> set[str]:
    """Node names reachable from `start` by following edges."""
    seen = {start}
    stack = [start]
    while stack:
        node = by_name.get(stack.pop())
        if node is None:
            continue
        for edge in node.edges:
            if edge.target in by_name and edge.target not in seen:
                seen.add(edge.target)
                stack.append(edge.target)
    return seen


def validate_agent(config: AgentConfig) -> list[ValidationFinding]:
    """Return every structural error and design-smell warning in the graph.

    Errors mirror AgentBuilder's compile-time rules (so filtering to them and
    raising reproduces the old behavior). Warnings are the extra checks that a
    compiler doesn't need but a human reviewer would want.
    """
    findings: list[ValidationFinding] = []
    nodes: list[Node] = config.nodes
    names = {n.name for n in nodes}
    by_name = {n.name: n for n in nodes}

    if not names:
        findings.append(ValidationFinding("error", "No nodes", "Agent has no nodes."))
        return findings  # nothing else can be meaningfully checked

    if config.initial_node not in names:
        findings.append(
            ValidationFinding(
                "error",
                "Start node undefined",
                f"initial_node '{config.initial_node}' is not a defined node.",
            )
        )

    # ---- errors: the exact rules AgentBuilder enforces, but collected ----
    for node in nodes:
        for edge in node.edges:
            if edge.target == node.name:
                findings.append(
                    ValidationFinding(
                        "warning",
                        "Self-loop edge",
                        f"Edge '{edge.function}' in node '{node.name}' points back to "
                        f"the same node — add a new node for this step instead "
                        f"(e.g. a lookup node before the node that offers options).",
                        node=node.name,
                        edge=edge.function,
                    )
                )
            if edge.target not in names:
                findings.append(
                    ValidationFinding(
                        "error",
                        "Edge to unknown node",
                        f"Edge '{edge.function}' in node '{node.name}' targets unknown "
                        f"node '{edge.target}'.",
                        node=node.name,
                        edge=edge.function,
                    )
                )

        if node.end and node.edges:
            findings.append(
                ValidationFinding(
                    "error",
                    "Terminal node has edges",
                    f"Node '{node.name}' has end=true but also has outgoing edges "
                    f"({', '.join(e.function for e in node.edges)}) — it would end the "
                    "call before those edges could ever be reached.",
                    node=node.name,
                )
            )

        functions = [e.function for e in node.edges]
        dupes = {f for f in functions if functions.count(f) > 1}
        if dupes:
            findings.append(
                ValidationFinding(
                    "error",
                    "Duplicate edge functions",
                    f"Node '{node.name}' has duplicate edge function name(s): "
                    f"{', '.join(sorted(dupes))} — the model can't tell them apart.",
                    node=node.name,
                )
            )

        reserved = RESERVED_FUNCTION_NAMES & set(functions)
        if reserved:
            findings.append(
                ValidationFinding(
                    "error",
                    "Reserved function name",
                    f"Node '{node.name}' uses reserved function name(s): "
                    f"{', '.join(sorted(reserved))} — these are auto-provided on every "
                    "non-terminal node for human escalation.",
                    node=node.name,
                )
            )

        for edge in node.edges:
            if edge.tool is not None and edge.tool not in TOOL_REGISTRY:
                findings.append(
                    ValidationFinding(
                        "error",
                        "Unknown tool",
                        f"Edge '{edge.function}' in node '{node.name}' names unknown tool "
                        f"'{edge.tool}' — must be one of {sorted(TOOL_REGISTRY)}.",
                        node=node.name,
                        edge=edge.function,
                    )
                )
            if edge.tool_async and edge.tool is None:
                findings.append(
                    ValidationFinding(
                        "error",
                        "Async without tool",
                        f"Edge '{edge.function}' in node '{node.name}' sets tool_async but "
                        "has no tool — tool_async is meaningless without one.",
                        node=node.name,
                        edge=edge.function,
                    )
                )

    # ---- warnings: reachability & flow smells (new "by hand" checks) ----
    if config.initial_node in names:
        reachable = _reachable_from(config.initial_node, by_name)
        for node in nodes:
            if node.name not in reachable:
                findings.append(
                    ValidationFinding(
                        "warning",
                        "Unreachable node",
                        f"Node '{node.name}' can't be reached from the start node "
                        f"'{config.initial_node}' by any path.",
                        node=node.name,
                    )
                )
        if not any(by_name[n].end for n in reachable):
            findings.append(
                ValidationFinding(
                    "warning",
                    "No way to end the call",
                    "No terminal node (end=true) is reachable from the start — the agent "
                    "has no natural way to hang up.",
                )
            )
        if by_name[config.initial_node].end:
            findings.append(
                ValidationFinding(
                    "warning",
                    "Call ends immediately",
                    f"The start node '{config.initial_node}' is terminal, so the call ends "
                    "before the caller can say anything.",
                    node=config.initial_node,
                )
            )

    for node in nodes:
        if not node.end and not node.edges:
            findings.append(
                ValidationFinding(
                    "warning",
                    "Dead-end node",
                    f"Node '{node.name}' isn't terminal but has no outgoing edges — once "
                    "here the caller can only be escalated to a human.",
                    node=node.name,
                )
            )
        if not _task_content(node):
            findings.append(
                ValidationFinding(
                    "warning",
                    "Empty instructions",
                    f"Node '{node.name}' has no task message, so the agent has nothing to "
                    "say or do there.",
                    node=node.name,
                )
            )
        for edge in node.edges:
            missing = [r for r in edge.required if r not in (edge.properties or {})]
            if missing:
                findings.append(
                    ValidationFinding(
                        "warning",
                        "Required field not collected",
                        f"Edge '{edge.function}' in node '{node.name}' marks "
                        f"{', '.join(missing)} as required but never declares "
                        f"{'it' if len(missing) == 1 else 'them'} as a collected field.",
                        node=node.name,
                        edge=edge.function,
                    )
                )

    return findings


def _normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


# Manual-only titles — if the deterministic pass already raised one at the same
# spot, drop LLM findings that echo the same structural theme.
_STRUCTURAL_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "no nodes": ("no nodes",),
    "start node undefined": ("start node", "initial node"),
    "edge to unknown node": ("unknown node", "dangling", "invalid target"),
    "self-loop edge": ("self-loop", "self loop", "loops back", "same node"),
    "terminal node has edges": ("terminal node", "end=true", "ends the call"),
    "duplicate edge functions": ("duplicate", "function name"),
    "reserved function name": ("reserved function", "request_human", "confirm_human"),
    "unknown tool": ("unknown tool",),
    "async without tool": ("tool_async", "async without"),
    "unreachable node": ("unreachable", "cannot be reached", "can't be reached"),
    "no way to end the call": ("no way to end", "no terminal"),
    "call ends immediately": ("ends immediately",),
    "dead-end node": ("dead end", "dead-end", "no outgoing"),
    "empty instructions": ("empty instruction", "no task message"),
    "required field not collected": ("required field", "not collected", "not declared"),
}


def _titles_overlap(a: str, b: str) -> bool:
    a, b = _normalize_title(a), _normalize_title(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    stop = {"a", "an", "the", "to", "in", "on", "is", "no", "not", "and", "or", "for"}
    aw = {w for w in a.split() if w not in stop}
    bw = {w for w in b.split() if w not in stop}
    if not aw or not bw:
        return False
    shared = aw & bw
    return len(shared) >= min(2, len(aw), len(bw))


def _same_location(a: dict, b: dict) -> bool:
    an, ae = (a.get("node") or "").lower(), (a.get("edge") or "").lower()
    bn, be = (b.get("node") or "").lower(), (b.get("edge") or "").lower()
    if not an or not bn or an != bn:
        return False
    if ae and be:
        return ae == be
    return True


def _structural_echo(llm: dict, manual: dict) -> bool:
    mt = _normalize_title(manual.get("title") or "")
    hints = _STRUCTURAL_TITLE_HINTS.get(mt)
    if not hints:
        return False
    lt = _normalize_title(llm.get("title") or "")
    return any(h in lt for h in hints)


def dedup_llm_findings(manual: list[dict], llm: list[dict]) -> list[dict]:
    """Drop LLM findings that repeat a deterministic finding at the same spot."""
    kept: list[dict] = []
    for llm_f in llm:
        if any(
            _same_location(llm_f, m)
            and (
                _titles_overlap(llm_f.get("title", ""), m.get("title", ""))
                or _structural_echo(llm_f, m)
            )
            for m in manual
        ):
            continue
        kept.append(llm_f)
    return kept

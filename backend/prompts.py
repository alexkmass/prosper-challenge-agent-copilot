from tools.registry import TOOL_REGISTRY


def _collect_hint(spec) -> str:
    required = spec.default_required
    optional = [k for k in spec.default_properties if k not in required]
    parts: list[str] = []
    if required:
        parts.append(f"Collect {'/'.join(f'`{r}`' for r in required)} (required)")
    if optional:
        parts.append(f"optionally {'/'.join(f'`{o}`' for o in optional)}")
    return ". " + ". ".join(parts) if parts else ""


def _format_tools_for_prompt() -> str:
    lines = [
        "Available tools — set an edge's `tool` field to one of these keys ONLY when the "
        "edge's job matches. These are the complete catalog — no other tool keys exist, and "
        "you must never invent names (e.g. there is no `reservation_save`; persisting a "
        "confirmed booking is `appointment_book`). Leave `tool` unset for plain routing edges. "
        "Use `collect` on a tool edge only for the fields that tool actually needs:",
    ]
    for key in sorted(TOOL_REGISTRY):
        spec = TOOL_REGISTRY[key]
        lines.append(f"- `{key}`: {spec.default_description.rstrip('.')}{_collect_hint(spec)}.")
    lines.append(
        "\nSet `tool_async: true` on an edge ONLY when the tool is a pure side effect "
        "whose result you don't need to react to in the same turn and don't need before "
        "a later step (e.g. `crm_create`, `send_sms`, `send_email`). Never set it on "
        "`appointment_lookup`, `appointment_book`, or `crm_lookup` — you need their "
        "result immediately to keep talking to the caller correctly, and an async call "
        "wouldn't be back in time."
    )
    return "\n".join(lines)


AGENT_DESIGN_RULES = (
    """
You design voice AI agents for Prosper, a company that builds phone-call AI \
agents for healthcare use cases (mainly appointment scheduling). An agent is \
a graph of nodes; each node is one step of the conversation, and each edge is \
a named function the LLM can call to transition to another node.

Rules:
- Every node needs a `task_message`: a short instruction for what the agent \
  should say or do at that step. Replies are spoken aloud, so avoid anything \
  that can't be read out (no lists, no emojis, no markdown).
- A node with no outgoing edges MUST have `end` set to true \
  (it ends the call). \
  A node with edges MUST have `end` set to false.
- `initial_node` must be the `name` of one of the nodes.
- Every edge's `target` must be the `name` of another node in the graph. \
  Never point an edge back to the same node it leaves — no self-loops. If a \
  step needs a tool side effect before the conversation can continue (e.g. \
  look up available slots before offering times), add a new node for that \
  work, wire an edge into it, then an edge forward to the node that speaks \
  to the caller — do not attach the tool as a loop on the current node.
- Use `collect` on an edge only for information the caller actually needs to \
  give (e.g. their name, a date) — most edges (simple routing) need none.
- Every edge's `function` name must be unique within its node — this is how \
  the model tells two branches apart at call time. Two edges on the same node \
  must never share a function name, even if their targets differ.
- Keep the graph as small as it can be while still covering the described \
  cases. Prefer 4-10 nodes.

"""
    + _format_tools_for_prompt()
    + """

Do NOT design any node/edge for "let me speak to a human" or for recovering \
from a misheard/failed turn — both are provided automatically on every node \
you design, outside this graph entirely. Never use `request_human_agent` or \
`confirm_human_transfer` as a function name.
"""
)


# ---- Copilot refinement chat ----------------------------------------------
#
# Before any agent is generated, the Copilot talks the deployment engineer
# through what they want — turning a rough one-liner into a precise brief that
# follows the design rules above, asking questions when something material is
# missing. Nothing is built until the engineer is satisfied and clicks Build;
# this chat only shapes the `brief` that then feeds /build or /improve.

_CHAT_OUTPUT_CONTRACT = """
Every turn, return:
- `reply`: your conversational message to the engineer. Warm, concise, plain \
  text. Ask at most two focused questions at a time, and only about things \
  that would genuinely change the agent — never interrogate. If the request is \
  already clear enough to act on, say so and stop asking.
- `brief`: the full, self-contained specification accumulated so far, written \
  as instructions a designer could build from without seeing this chat. Fold \
  every decision made in the conversation into it and rewrite it each turn — \
  it is the ONLY thing passed to the builder, so anything not in the brief is \
  lost. Follow the design rules above (speakable replies, appropriate tools, \
  escalation handled automatically, etc.).
- `ready`: true once the brief is complete enough to build a good agent \
  without guessing at anything important. Prefer to reach `ready` quickly — \
  a sensible default stated in the brief beats another question. It is always \
  fine for the engineer to build anyway.
- `plan`: when (and only when) `ready` is true, a short list of plain-language \
  bullet points describing what building this will actually do — the concrete \
  steps or changes the engineer is about to approve. Empty list otherwise.
"""

_CHAT_TOOL_RULES = """
When you mention tools in `reply` or describe them in `brief`/`plan`, use ONLY \
keys from `available_tools` in the context JSON. Map colloquial requests to the \
closest real tool — e.g. "save the reservation", "confirm the appointment", or \
"persist the booking" means `appointment_book`, not a made-up tool. If nothing \
fits, say so and describe a plain routing edge instead.
"""

CHAT_BUILD_RULES = (
    AGENT_DESIGN_RULES
    + """
You are helping a deployment engineer turn a client's guidelines into a brand \
new voice agent. Interpret their description, propose sensible structure, and \
surface the decisions that matter: what the caller can accomplish, what \
information to collect, which tools apply, and how branches end. Assume good \
healthcare-scheduling defaults rather than blocking on every detail.
"""
    + _CHAT_TOOL_RULES
    + _CHAT_OUTPUT_CONTRACT
)

CHAT_IMPROVE_RULES = (
    AGENT_DESIGN_RULES
    + """
You are helping a deployment engineer improve an EXISTING voice agent, whose \
current graph (JSON) is provided. They will describe a change in their own \
words — sometimes prompted by a specific problem found in a call transcript \
(also provided when present). Ground every suggestion in the current graph: \
name the specific nodes and edges involved, and keep the change as minimal and \
targeted as the request allows. The `brief` you produce must describe the \
change precisely enough that the builder can return the entire corrected agent \
with everything else untouched.
"""
    + _CHAT_TOOL_RULES
    + _CHAT_OUTPUT_CONTRACT
)


# ---- Validation review (the LLM layer of the Validate feature) -------------
#
# Deterministic checks (agent_builder/validation.py) already cover the structural
# rules — dangling edges, dead ends, unreachable nodes, duplicate/reserved
# function names. This prompt is the judgment layer on top: is this a GOOD voice
# agent, not just a valid one? It reviews design quality and returns findings the
# engineer can act on, ideally by handing them to the Improve chat.

VALIDATION_RULES = (
    AGENT_DESIGN_RULES
    + """
You are reviewing the voice agent below (its node graph, as JSON) the way a \
senior conversation designer would before it ships. Judge whether it is a GOOD \
agent to put on a real phone call, not merely a valid one.

Look for design problems such as:
- Caller intents the graph doesn't handle: a plausible thing a caller would say \
  or want that has no branch (e.g. reschedule, cancel, ask about hours, "I'm not \
  a patient yet"). Missing coverage is the most valuable thing to catch.
- Rigid or brittle steps: a node that offers only fixed options with no fallback \
  when none fit, or that will have to make something up.
- Information collected too early, too late, or not at all for what a later step \
  (or tool) needs.
- Tools misused: a lookup/booking that should run but doesn't, a tool on the \
  wrong edge, an edge that loops back to its own source node instead of using \
  a dedicated node for that step, or an async tool whose result is actually \
  needed this turn.
- Instructions that are vague, off-persona, or not speakable (lists, markdown).
- Confirmation/verification gaps before an action with real consequences.

Do NOT report:
- Anything the deterministic validator already covers (dangling edges, dead \
  ends, unreachable nodes, duplicate or reserved function names, end+edges) — \
  assume those are handled elsewhere; focus on judgment, not structure.
- Missing "talk to a human" or error-recovery handling — both are provided \
  automatically on every node and must never be authored.

Return a list of `findings`. For each: a `severity` ("error" only for something \
that will clearly break a real call, otherwise "warning", or "info" for a minor \
polish note), a short `title`, a plain-language `detail` a non-engineer can \
follow, the `node` (and `edge` function, if applicable) it concerns when \
localized, and a concrete `suggestion` for how to fix it. If the agent is \
genuinely in good shape, return an empty list rather than inventing problems.
"""
)

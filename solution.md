# Solution

A voice agent builder (Phase 1) plus an Agent Copilot (Phase 2) that treats a voice agent's node
graph the way a coding agent treats a codebase: it proposes a full replacement, you see a diff, you
apply it or you don't.

## What's built

**Phase 1 — Voice Agent Builder** (`frontend/`, React + React Flow + shadcn/ui)
- Create, list, and switch between agents; edit agent-level settings (persona, model, voice).
- Click a node to edit its instructions, toggle whether it ends the call, rename it, set it as the
  start node, or delete it (cascades any edges pointing at it).
- Click an edge to edit its function name, target, trigger description, and the structured fields it
  collects (name / type / description / required) — no raw JSON editing.
- Add nodes with a button; add edges by dragging a connection on the canvas (or from a node's
  inspector) — both open the edge inspector pre-filled, ready to describe the transition.
- **Test call**: saves the current draft, marks it active, and opens Pipecat's prebuilt client in a
  new tab. (An embedded iframe was tried first, but Pipecat's client checks the browser's microphone
  permission state before deciding whether to prompt, and inside an iframe that check can report
  "denied" even when the top-level page already has access — so it silently never asked, and the fix
  lives inside Pipecat's bundled client, not this code. A new tab sidesteps it entirely.)
- Nodes are draggable to rearrange the layout for clarity; positions live only in the browser (never
  written to the saved agent) and reset when switching agents or via a **Reorder** button.
- **Call log**: since the test call runs in its own tab with no shared state with the builder, a
  "Call log" panel (polling `GET /api/calls/log`) shows what the agent actually collected during the
  current or most recent call — every node visited, the edge function that got it there, and the
  accumulated fields (name, insurance status, member ID, etc.) across the whole conversation.

**Phase 2 — Agent Copilot** (`backend/copilot.py`, a panel in the same UI)
- **Build**: paste a client's natural-language guidelines → the Copilot designs a full node graph.
  Generating always replaces the *entire* open agent — there's no partial merge — so if it already has
  real content, this requires an explicit confirmation before the generation call is even made.
- **Improve**: scans a batch of (mocked) call transcripts against the current agent automatically (no
  manual click — requiring one would undercut the point of automating detection) and surfaces an
  **Issue Inbox** — each issue attributed to the specific node where the agent mishandled the call,
  with the evidencing quote. Click an issue → the Copilot proposes a fix.
- Both modes feed the same review step: the proposed agent is diffed — client-side, not by the LLM,
  so the diff can't misdescribe its own change — against the current draft and rendered on the canvas
  as a color overlay (green = added, amber = modified, red = removed), with a plain-English change
  list in the side panel. Nothing is saved until you click **Apply**, then **Save**.

## Architecture

```
frontend (Vite/React)  --/api-->  FastAPI (bot.py + api.py + copilot.py)
                                        |
                                store.py (in-memory AgentStore)
                                        |
                          AgentBuilder.from_dict()  ->  Pipecat Flows graph  ->  voice call
```

- **Agent schema is untouched.** `backend/agent_builder/schema.py` and `builder.py` are exactly what
  shipped in the starter repo. Both the human editor and the Copilot read and write the same
  `AgentConfig` JSON — there's no separate "AI format."
- **`AgentStore`** (`backend/store.py`) is a small interface (`list`/`get`/`create`/`update`/
  `get_active_id`/`set_active_id`) with one in-memory implementation, seeded from the two example
  flows. Swapping in a real database later means writing one class, not touching `api.py` or `bot.py`.
- **No restart needed to test an edit.** Pipecat's dev runner invokes `bot()` fresh on every new
  WebRTC connection rather than once at process start. `bot.py` resolves the store's active agent
  *inside* `bot()`, so a save is live on the very next test call.
- **The Copilot never talks to the store directly.** `copilot.py`'s three endpoints (`/build`,
  `/audit`, `/fix`) each return a candidate `AgentConfig`, validated server-side with the exact same
  `AgentBuilder` check a human-edited save has to pass — including two rules added after real bugs
  surfaced them: edge function names must be unique within a node (the LLM once emitted two
  identically-named tools on one node, breaking its own ability to tell them apart), and a node with
  `end: true` can't also have edges (this one crashed a real test call the instant it was reached,
  since Pipecat ends the call the moment such a node is entered — not after the user responds). The
  frontend owns the apply step — the LLM proposes, the human disposes.

## Why this Copilot design

The brief names two burdens: turning guidelines into a working agent, and finding + fixing problems
in production — including that *finding* them is itself a burden. A single "generate the whole agent
from a prompt" tool only solves the first one, and a chatbot that free-edits the graph on request
doesn't solve the detection problem at all — someone still has to notice something's wrong and
describe it.

So the Improve mode does the noticing: it audits a batch of calls against the live graph and returns
issues with an attributed node and a quoted line of evidence — the same first step a human reviewer
would do, but instant. And because both modes converge on the same "propose full graph → diff →
apply" mechanic, the deployment team learns one interaction pattern that covers "build this from
scratch" and "here's what's broken, fix it" — not two different tools bolted together.

## What's mocked, deferred, or cut, and why

- **Call data is mocked** (`backend/mock_calls.json`, 4 transcripts) — explicitly permitted by the
  brief. Each transcript was written to expose a *different class* of real problem (a mid-flow intent
  switch with no escape edge, rigid options with no fallback, an out-of-scope question answered
  instead of deferred, a required field with no alternate lookup), not just cosmetic issues. The
  audit and fix themselves are live LLM calls every time — only the input calls are canned.
- **No live fallback for the Copilot demo.** Every Build/Improve action is a real OpenAI call with no
  pre-baked backup if the API hiccups during a live review. Chosen for authenticity over safety net.
- **No node position *persistence*.** Layout is always recomputed from the graph structure (BFS depth
  from the start node) and manual drag positions live only in the browser — neither is ever written to
  the saved agent JSON. Persisting `{x, y}` would put a UI concern inside the contract the backend and
  the Copilot both read.
- **No undo/redo, no multi-user/auth, no agent deletion from the picker, no streaming Copilot
  output.** None of these change whether the core problem — turning guidelines into an agent, and
  turning call issues into a fix — gets solved, and the review explicitly asked for a demo, not a
  feature-complete builder.
- **The Copilot is single-shot per action, not an open-ended chat.** Each Build or Improve action is
  one generation, reviewed once. This was a deliberate choice to keep "review a proposed diff" as the
  one central mechanic rather than adding a second, looser interaction style (chat) alongside it.

## Testing

`backend/tests/` — the split mirrors how conversational/voice agents are actually tested in
practice: component-level unit tests for the deterministic parts, and eval-style tests (real LLM
calls, assert on the outcome) for the decision layer, rather than driving audio/telephony.

- **Unit tests** (`test_agent_builder.py`, no API calls): the schema/compiler layer — valid agents
  load, invalid ones (missing `initial_node`, a dangling edge target, duplicate edge function names,
  a node with `end: true` that also has edges — the exact bug that crashed a real test call) are
  rejected before they ever reach a live call.
- **Eval tests** (`test_tool_calling.py`, `test_copilot.py`, real OpenAI calls, `@pytest.mark.llm`):
  given a node's actual persona/task/tool schema, does the LLM pick the correct edge (path
  selection), extract arguments correctly, and hold off calling a tool when required information is
  missing? Same bar applied to the Copilot's build/audit/fix output. The tool schema under test is
  derived from Pipecat's own `OpenAILLMAdapter`, not reimplemented, so there's no drift between what
  gets tested and what actually runs.

`make test-fast` / `make test-llm` / `make test` run these from the repo root.

## Demo flow

1. Open the branched example agent, click through a node and an edge to show the inspector.
2. Copilot → **Improve** → Scan calls → walk through 1-2 issues in the inbox (node attribution +
   quoted evidence) → Propose fix → point at the green/amber diff on the canvas → Apply → Save.
3. Test call the fixed agent live.
4. Create a new agent, Copilot → **Build** → paste guidelines → watch a full graph appear as an
   all-green diff → Apply → Save → Test call.

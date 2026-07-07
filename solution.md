# Solution

A voice agent builder (Phase 1) plus an Agent Copilot (Phase 2) that treats a voice agent's node
graph the way a coding agent treats a codebase: it proposes a full replacement, you see a diff, you
apply it or you don't.

## What's built

**Phase 1 — Voice Agent Builder** (`frontend/`, React + React Flow)
- Visual graph editor: create/switch agents, edit nodes, edges, and agent settings (persona, model,
  voice) — including optional tools on edges (see Tools below). No raw JSON.
- **Test call** saves the current draft, marks it active, and opens Pipecat's prebuilt client in a
  new tab.
- **Layout is session-only** — positions are computed from graph structure (BFS) plus manual drag;
  neither is saved to the agent JSON, so the backend/Copilot contract stays clean.
- **Call log** — the test call runs in a separate tab, so the builder polls `GET /api/calls` for a
  per-session history (transcript, node path, collected state, pipeline metrics).

**Phase 2 — Agent Copilot** (`backend/routes/copilot.py`)

The Copilot has two layers: a **refinement chat** that turns rough input into a production-ready
`brief`, and a **generation step** that emits a whole agent from that brief. Build, Improve, and
Validate all converge on the same review mechanic at the end.

**Build / Improve / Validate — what each is for**

| Mode | How a fix/build starts | What gets iterated |
| --- | --- | --- |
| **Build** | Engineer pastes client guidelines ("callers should be able to reschedule…") | Chat turns vague client language into a complete agent spec |
| **Improve** | Free-text request, or an audited call issue (inbox), or validation findings handed over from Validate | Chat grounds the request in the *current* graph and tightens the change |
| **Validate** | Engineer clicks Validate on the canvas | No chat yet — runs checks on the draft; selected findings seed Improve's chat |

In every case where generation happens, the engineer can **iterate in chat** before committing:
each `/chat` turn rewrites the accumulated `brief` (the only text that reaches `/build` or
`/improve`), asks at most a couple of focused questions, and — once `ready` — returns a
plain-language **plan** (bullet list of what building will actually do). "Keep iterating" sends
you back to chat; "Build it" is the gate before any graph is produced.

**The prompt filter (chat layer)**

Engineers type in their own words; the model does not edit the graph directly. Instead,
`CHAT_BUILD_RULES` / `CHAT_IMPROVE_RULES` (both built on `AGENT_DESIGN_RULES` — speakable replies,
valid tools, no self-loops, 4–10 nodes, etc.) instruct the chat to:

- translate client-speak into deployable agent requirements ("save the reservation" →
  `appointment_book`, not an invented tool);
- fold every decision into a self-contained `brief` each turn — anything not in the brief is lost
  at generation time;
- for Improve, name the specific nodes/edges involved and keep the requested change minimal.

Improve chat also receives the **current graph JSON**, `available_tools`, and (when relevant) the
audited issue + transcript — so refinement is grounded in what actually exists, not a blank slate.

**Generation → review (what the engineer actually sees)**

Once the plan is approved:

1. **`/build` or `/improve`** receives the `brief` plus, for Improve, the full current agent.
   `AGENT_DESIGN_RULES` + a whole-agent-edit instruction tell the model to return the **entire**
   corrected graph — copy every untouched node/edge exactly, change only what's needed — plus an
   `explanation` in plain English.
2. **Why a full graph, not a patch?** Structured output is reliable at emitting a complete
   `AgentConfig`, not a surgical diff. Asking for "only the changed nodes" risks dropped edges,
   broken `initial_node` references, and merge bugs. Returning the whole agent and diffing locally
   is the same pattern as a coding agent proposing a full file: the human reviews a precise change
   set without trusting the model to describe it accurately.
3. **Review surfaces three complementary views:**
   - **Explanation** ("What changed & why") — readable narrative from the model, for context; not
     authoritative.
   - **Exact changes** — a bullet list from `summarizeDiff()`, computed client-side by comparing
     old vs. new JSON node-by-node and edge-by-edge.
   - **Canvas overlay** — green / amber / red on nodes and edges so you can *see* the change set on
     the graph without reading JSON.
4. **Apply** swaps the in-memory draft; **Save** persists via the normal `PUT` path.

Improve also **auto-audits** mocked call transcripts on tab open (`example_flow2` only) and surfaces
an issue inbox — node attribution plus a quoted line of evidence — as another way to seed the chat.

**Tools** (`backend/tools/`)
- Edges can call a fixed catalog (appointments, CRM, SMS/email); results reach the LLM in the same
  turn. **`tool_async`** fires pure side effects in the background — result lands in `flow_manager.state`
  for a later turn, never the current reply. Lookups/bookings must stay sync.
- One **`tool_catalog()`** feeds the edge picker (`GET /api/tools/catalog`) and Copilot chat context
  (`available_tools`) — no duplicated tool list, no tools panel in the UI.
- **Human escalation** (`request_human_agent` → `confirm_human_transfer`) and **call resilience**
  ("could you say that again?") are injected automatically — never authored in the graph. Per-node
  globals vs pipeline-wide behavior; see [agent-tools.md](specs/agent-tools.md). CRM contact
  creation also runs post-call as a deterministic fallback if nothing created it mid-call.

## Architecture

```
frontend (Vite/React)  --/api-->  FastAPI (bot.py + routes/)
                                        |
                                store.py (in-memory AgentStore)
                                        |
                          AgentBuilder.from_dict()  ->  Pipecat Flows graph  ->  voice call
```

- **One `AgentConfig` JSON** for UI, Copilot, and runtime. `Edge` was extended with `tool` /
  `tool_async`; Copilot structured output converts at the API boundary — no separate AI format.
- **`validation.py`** is the single source for structural checks; `AgentBuilder` raises on errors,
  `/validate` returns errors + warnings + an LLM design pass.
- **Active agent resolves per WebRTC connection** inside `bot()` — save is live on the next test call,
  no backend restart.
- **Prompts centralized** in `prompts.py` (`AGENT_DESIGN_RULES` shared by build, improve, chat,
  validate) — real tool keys only, no self-loops.
- **Stores are interfaces, not databases** — `AgentStore` and `CallStore` are small `Protocol`s with
  in-memory implementations for the challenge (agents and call history are lost on restart). Production
  swaps in a real DB behind the same methods without touching `api.py`, `bot.py`, or the UI.

## Key decisions (challenge scope)

**Improve audits mock calls; the call log is separate.** The inbox demonstrates *automatic issue
detection* using four canned transcripts for `example_flow2`. Real test calls land in `CallStore`
with full metrics but are not fed back into Improve yet — see [In production](#in-production).


**Notifications: tools exist, product wiring is thin.** `send_sms`, `send_email`, and a reminder
scheduler are implemented (dummy outbox + `appointment_book` queues a fixed pre-appointment
reminder). The example agents don't send a confirmation text on book — prod wiring is under
[In production](#in-production).

**Testing without audio.** CI doesn't drive STT/TTS or WebRTC. Fast tests cover deterministic
logic; LLM evals (`make test-llm`) send text user turns to the real model + Pipecat's tool schema
and assert path/tool selection. Voice is left to manual test calls.

## Why this Copilot design

The brief names two burdens: building agents from guidelines, and finding + fixing production problems.
**Improve** (call audit) and **Validate** (draft review) automate the *finding* step; both feed the
same chat → whole-graph generate → diff → apply loop described above — one interaction pattern, not
three separate tools.

## Spec-driven development

[`specs/`](specs/README.md) holds one document per feature area — contracts, requirements, and
acceptance criteria that define "done." This repo was built quickly first; going forward the rule is
**spec → code → tests**: change the spec before the behavior, then keep acceptance criteria mapped
to something checkable (`backend/tests/` or a scripted manual step). The specs are the detailed source of truth.

## In production

What we'd build next, on top of the same architecture — not in the challenge repo.

**Persistence** — Postgres (or similar) behind the existing `AgentStore` / `CallStore` protocols;
agents, call history, metrics, and clinic config survive restarts.

**Improve from flagged real calls** — Same inbox → chat → diff flow, fed from automatic analysis of
stored calls that get flagged (human transfer, fatal errors, repeated tool failure, low QA score, etc.)
— not only `mock_calls.json`.

**Escalation policy** — Track human-transfer rate per agent/version. If most calls are escalated,
alert and tighten global escalation (or route the graph fix through Improve). Challenge: confirm-once
flow is injected on every node; no rate cap or metrics-driven policy yet.

**Performance** — Cache compiled agents (Pipecat graph / `AgentBuilder` output keyed by
`agent_id + config hash`), invalidate on save. Cuts load latency on the hot path before touching
infra scale-out.

**Observability** — **Cross-call aggregates**: volume, avg duration, message count, escalation rate,
per-tool usage, error rate — across sessions, not only inside one call log entry. If LLM/STT/TTS
bucket totals aren't enough to explain latency, add **turn-level timing** (STT end → LLM start → tool
handlers → TTS start) so we can see where time actually goes.

**Clinic layer + RAG** — Multi-tenant: **per-clinic view of agents** plus a **shared knowledge base**
(vector store + UI for editors) injected into every agent for that clinic. Good RAG candidates:
hours, locations, insurance accepted, policies, FAQs, seasonal notices. Keep out of RAG: live slots,
CRM records, eligibility — those stay in tools/EHR. Graph structure remains per-agent; clinic context
is shared and versioned separately.

**Agent versioning & A/B** — Don't keep a single live config per logical agent. Store multiple
versions, route a **traffic share** to each, and compare metrics (completion, escalation, duration,
tool success). Sticky assignment per caller, promote/rollback, and a history of what actually shipped
— the natural prod evolution of "propose whole graph → review diff → apply."

**Notifications (prod wiring)** — On successful book, fire **async** confirmation SMS/email (tools
already support it; example flows don't wire it yet). Reminders move to a real scheduler with real
gateways — offset/timing becomes **clinic configuration**, not hard-coded in the demo.

**Review bookings** — Ops-facing view of bookings (today: dev-only `GET /api/tools/bookings`). In prod:
a panel or dashboard for clinic staff, not something every deployment engineer needs in the builder.

## What's mocked, deferred, or cut

See [In production](#in-production) for the intentional next steps. In the challenge itself:

- **Mock call data** (`mock_calls.json`, 4 transcripts for `example_flow2`) — audit/fix are live LLM
  calls; only inputs are canned.
- **No Copilot fallback** on API failure — real calls throughout the demo.
- **No layout persistence, undo/redo, auth, multi-tenant clinics, agent deletion, streaming Copilot
  output** — demo scope.
- **Stateless `/chat`** — frontend replays history each turn; no server sessions.
- **No surgical graph edits via chat** — whole-agent generation + diff review keeps one mechanic.
- **No reusable conversation blocks, knowledge base, A/B routing, or cross-call analytics UI** —
  documented under In production.

## Testing

`make test-fast` (73 tests) / `make test-llm` (12 tests). See **Testing without audio** under
[Key decisions](#key-decisions-challenge-scope).

## Demo flow

1. Branched example agent → quick tour of the graph editor.
2. **Validate** → pick findings → **Fix in Improve chat** → diff → Apply → Save.
3. **Improve** → inbox issue → seed chat → diff → Apply.
4. **Test call** → **Call log** (path, state, metrics).
5. New agent → **Build** chat → plan → all-green diff → Apply → Test call.

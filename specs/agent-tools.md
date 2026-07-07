# Agent Tools

**Status:** Implemented. Source of truth for `backend/tools/` and the `tool`/`tool_async` fields on
`Edge` — update this spec before changing either.

## Overview

Before this spec, an `Edge` (see [agent-schema-and-builder.md](agent-schema-and-builder.md)) was
only ever a transition: the LLM calls it, whatever it collected gets merged into
`flow_manager.state`, and the graph moves to `target`. Nothing an agent did had a real side effect.

This spec adds **tools**: backend-implemented capabilities with actual (dummy-backed) side
effects — looking up appointment slots, booking one, checking/creating a CRM contact, sending a
text or email — that a human (or the Copilot) attaches to an edge from a fixed catalog, plus two
capabilities that apply automatically to every agent regardless of its authored graph: escalating
to a human, and recovering from a flaky STT/LLM/TTS call.

A tool can also run **in the background** (`tool_async`) instead of blocking the turn on its
result — see "Sync vs. async" below for when that's the right call, and the "Prosper Scheduler
(Branched)" section for a worked example (create the CRM contact while the conversation moves on,
so it's ready to link into the booking a couple of turns later).

## Goals

- Give edges real backend behavior without a second "AI format" — a tool-carrying edge is still
  exactly the `Edge` shape in `agent-schema-and-builder.md`, just with two more fields.
- Every store behind a tool (bookings, CRM) is a small `Protocol` + one in-memory implementation,
  mirroring `backend/store.py` — swapping in a real database later means writing one class.
- Picking a tool for an edge is a first-class, low-friction UI action (a dropdown with sensible
  defaults), not raw JSON — most agents will use at least one or two of these.
- Escalation-to-human and call resilience apply to every agent automatically; nobody has to author
  them into the graph.
- A tool whose result doesn't need to shape what's said *right now* shouldn't make the caller wait
  for it.

## Non-goals

- A real database, SMS gateway, or email provider — everything here is an in-memory dummy behind a
  `Protocol`, matching the brief's allowance for mocked infrastructure.
- A frontend dashboard over tool activity (bookings, CRM, outbox, reminders). The dev endpoints
  below exist for verification/demo, not as a built UI panel.
- Real-world-timed reminders. A booking schedules a reminder for `slot.start - 1h`, but since demo
  bookings are for future days, nothing fires during a live demo without the manual endpoint below.
- Multiple tools on one edge. An edge carries at most one `tool`; a conversation step that needs two
  side effects (like the branched example below) spreads them across the edges it already has,
  rather than the schema growing a tool *list*.
- Surfacing a background tool's failure to the caller. If a `tool_async` call raises, it's logged,
  not spoken — the turn that triggered it already finished responding.

## Requirements

### Tool registry (edge-level tools)

`backend/tools/registry.py` exposes `TOOL_REGISTRY: dict[str, ToolSpec]` and `tool_catalog()`,
which serializes the registry for API/UI/Copilot consumers. Each `ToolSpec` carries a
`key`, a UI `label`/`category`, suggested `default_function`/`default_description`/
`default_properties`/`default_required` (used to prefill an edge when the tool is picked in the
UI), and a `handler(args: dict, state: dict) -> dict` coroutine.

| Key | Category | Backing store | What it does |
| --- | --- | --- | --- |
| `appointment_lookup` | Appointments | `booking_store` | Lists available slots, optionally filtered by `service`/`date`. Returns `available_slots`. |
| `appointment_book` | Appointments | `booking_store` | Books a slot for a caller and schedules a 1-hour-before reminder when contact info is present. Returns `booking_id` + `confirmed_slot`. See FR-7 for how it resolves *which* slot. |
| `crm_lookup` | CRM | `crm_store` | Looks up a contact by name. Returns `crm_found` (bool) + `contact` (or `None`). |
| `crm_create` | CRM | `crm_store` | Creates a contact, or returns the existing one if already present (idempotent — safe to call even after `crm_lookup`). Returns `crm_contact_id` + `crm_created` (bool). |
| `send_sms` | Notifications | `notifications` | Sends a text via `MockSmsSender`. Falls back to `state["phone_number"]` if `phone_number` isn't in the edge's own args. |
| `send_email` | Notifications | `notifications` | Sends an email via `MockEmailSender`. Falls back to `state["email"]` the same way. |

- **FR-1**: `Edge.tool`, if set, must be a key in `TOOL_REGISTRY` — `AgentBuilder` rejects an
  unknown key at validation time (see [agent-schema-and-builder.md](agent-schema-and-builder.md)).
- **FR-2**: When a **synchronous** tool edge's function is called (`tool` set, `tool_async` unset or
  `false`), `AgentBuilder` awaits the tool's `handler(args, state)` **before** merging: the handler's
  return dict is merged with the collected `args` (`{**args, **tool_result}`) and *that* merged
  dict — not just `args` — becomes both the function's return value to the LLM and what's merged
  into `flow_manager.state`. This is why `crm_lookup`'s `crm_found` is visible to the model in the
  very same turn even though the edge still transitions to a single `target` regardless of
  found/not-found — the model reacts to the tool's JSON result, not to which node it lands on.
- **FR-3**: A tool handler raises a plain `ValueError` with a speakable message on failure (e.g. "That
  slot isn't available anymore — please choose another time."). No handler needs its own
  try/except: Pipecat Flows already catches any exception raised inside a function handler and
  returns `{"status": "error", "error": ...}` to the LLM instead of crashing the call — the model
  sees the message and can apologize/retry in-conversation. (This safety net only covers
  synchronous tools — see FR-5 for the async case.)
- **FR-4**: `appointment_book` picks a reminder channel from whatever contact info is present
  (`phone_number` preferred, else `email`) and skips scheduling if neither is available, or if the
  booking isn't tied to a real datetime (FR-7's label fallback) — it never fails the booking itself
  over a missing contact channel or a missing reminder time.

### Sync vs. async (`Edge.tool_async`)

- **FR-5**: `Edge.tool_async: bool = False`. When `true`, taking the edge does **not** await the
  tool: it fires the handler as a background `asyncio` task and immediately proceeds with just the
  collected `args` — the LLM's response for this turn, and the transition, never wait on it.
  Once the background task finishes, its result is merged into `flow_manager.state` only (never
  into an LLM response, since that turn is long over) — visible to any *later* tool handler that
  reads `state`, and to nothing else. A background failure is logged, not surfaced (see Non-goals).
  `AgentBuilder._validate()` rejects `tool_async: true` on an edge with no `tool` set — the flag is
  meaningless without one.
- **FR-6**: Whether to set `tool_async` is a judgment call per edge, not a property of the tool
  itself — the same tool could reasonably be sync in one graph and async in another. The rule of
  thumb: set it **only** when the caller doesn't need the model to react to the result right now and
  nothing later in *this same turn* depends on it — a pure side effect like `crm_create`,
  `send_sms`, or `send_email`. Never set it on `appointment_lookup`, `appointment_book`, or
  `crm_lookup` — their whole purpose is to inform what the model says next, so awaiting them is the
  point, not a cost to avoid. (An earlier idea — queue every tool call and run them all after the
  call ends — doesn't work for this: a booking that wants to reference the CRM contact needs it to
  exist *before* the call ends, not after.)

### CRM store (`backend/tools/crm_store.py`)

- `CrmStore` protocol: `find_by_name(first_name, last_name) -> dict | None`,
  `create_contact(first_name, last_name, insurance_id=None, phone_number=None, email=None) -> dict`,
  `list_contacts() -> list[dict]`.
- `InMemoryCrmStore` is seeded with a couple of example contacts so `crm_lookup` has something to
  find during a demo.
- **FR-7**: Both `crm_lookup` and `crm_create` resolve the caller's name via
  `tools/handlers.py`'s `resolve_full_name(args, state)`: prefer explicit `first_name`/`last_name`
  if the edge collected them, else split a `full_name` (from either `args` or `state`) on the first
  space. This lets an edge that only ever collected a single `full_name` field (like the branched
  scheduler example) still drive both CRM tools with no schema change.
- **FR-8**: `crm_create` is idempotent: it looks the contact up first and returns the existing
  `crm_contact_id` (with `crm_created: false`) rather than creating a duplicate — safe to call
  unconditionally even on a node a prior `crm_lookup` already ran on.
- **FR-9**: Creating a contact that was never explicitly created mid-call is **also** available as a
  fallback that isn't a tool call at all — it happens once the call ends, if nothing already did it.
  `bot.py`'s `finally` block after `await runner.run()` (same place that calls `call_store.end_call`,
  see FR-16 in [voice-agent-builder-ui.md](voice-agent-builder-ui.md)) inspects
  `call_store.get(call_id)["state"]` — the same accumulator the Call Log panel reads; if
  `crm_found` is `False`, no `crm_contact_id` is already in state (meaning a `crm_create` edge
  didn't already handle it), and a name was collected, it calls `crm_store.create_contact(...)`
  with whatever of `insurance_id`/`phone_number`/`email` is present. No LLM or tool involvement in
  this step, and it never runs a second time if `crm_create` already did the job mid-call.

### Booking store (`backend/tools/booking_store.py`)

- `BookingStore` protocol: `list_available_slots(service=None, date=None) -> list[dict]`,
  `book_slot(slot_id, caller_name, phone=None, email=None, crm_contact_id=None) -> dict`,
  `book_label(label, caller_name, phone=None, email=None, crm_contact_id=None) -> dict`,
  `list_bookings() -> list[dict]`.
- `InMemoryBookingStore` is seeded with slots across a couple of services over the next several
  days. Booking a slot marks it unavailable; booking an already-taken or unknown `slot_id` raises
  `ValueError` (see FR-3).
- **FR-10**: `appointment_book`'s handler resolves *which* slot two ways: if the edge collected a
  real `slot_id` (from a prior `appointment_lookup`), it calls `book_slot`. If not — e.g. an edge
  offering a small fixed menu that was never backed by a live lookup — it falls back to whatever
  free-text `slot`/`time_label` the edge collected and calls `book_label` instead, which records the
  booking without a reminder (a label isn't a real datetime to count 1 hour back from). Either way,
  the booking also carries `state.get("crm_contact_id")` if one is already there — see the worked
  example below for where that comes from.

### Notifications (`backend/tools/notifications.py`) + reminders (`backend/tools/scheduler.py`)

- `SmsSender`/`EmailSender` protocols; `MockSmsSender`/`MockEmailSender` record every send to an
  in-memory outbox (and log it) instead of calling a real gateway/provider.
- `ReminderScheduler` protocol: `schedule(run_at, channel, to, message) -> dict`,
  `list() -> list[dict]`, `fire(reminder_id) -> dict`. `InMemoryReminderScheduler` lazily starts a
  background asyncio loop (on first `schedule()` call) that fires due reminders through the same
  mock senders `send_sms`/`send_email` use.

### Escalate to a human (global, not schema-visible)

- **FR-11**: `AgentBuilder._make_node` appends two `FlowsFunctionSchema`s to every compiled node
  whose `end` is `False` — these are not part of `AgentConfig`/`nodes`, so no agent author (human or
  Copilot) ever needs to add them:
  - `request_human_agent` (no properties): its handler returns a plain dict (no node) — Pipecat
    Flows treats a handler that returns just a result as "stay on this node." The dict instructs the
    LLM to ask the caller to confirm before transferring and to mention it can still help with the
    current topic, and explicitly to prefer a more specific escalation/transfer edge already on the
    node instead, if one matches the situation better (see the acceptance criteria below for why).
  - `confirm_human_transfer` (no properties): its handler runs a dummy `connect_to_human(state)`
    (logs a mock ticket id) and returns a synthetic terminal `NodeConfig`, built directly in
    `builder.py` (never part of the saved agent), that says goodbye and ends the call.
- **FR-12**: `request_human_agent` and `confirm_human_transfer` are reserved function names —
  `AgentBuilder._validate()` rejects any user-authored edge on any node that reuses either name,
  since it would collide with the auto-injected pair.

### Call resilience (global, pipeline-level — not a tool at all)

- **FR-13**: `backend/tools/resilience.py`'s `CallResilienceProcessor` is inserted into `bot.py`'s
  pipeline immediately before `transport.output()`. It intercepts non-fatal `ErrorFrame`s (pushed
  downstream by the ElevenLabs STT/TTS services and the base LLM service on a failed request) and,
  instead of letting the failure dead-end the turn, pushes a `TTSSpeakFrame` with a generic
  recovery line ("Sorry, I had trouble with that — could you say that again?") so the call
  continues. A **fatal** `ErrorFrame` is passed through unchanged — that class of error is
  unrecoverable by design in Pipecat, and swallowing it would hide a real shutdown.

### Dev/verification endpoints (`backend/routes/tools.py`, prefix `/api/tools`)

Read-only visibility into the dummy backends, for manual verification and demoing — no dedicated
frontend panel:

| Method & path | Purpose |
| --- | --- |
| `GET /api/tools/catalog` | Edge-tool metadata for the UI picker and Copilot chat (`tool_catalog()`) |
| `GET /api/tools/slots` | Available slots (optional `service`, `date` query params) |
| `GET /api/tools/bookings` | All bookings made so far |
| `GET /api/tools/crm` | All CRM contacts (seeded + auto-created) |
| `GET /api/tools/outbox/sms` | Every mock SMS "sent" |
| `GET /api/tools/outbox/email` | Every mock email "sent" |
| `GET /api/tools/reminders` | Every scheduled reminder + its status |
| `POST /api/tools/reminders/{id}/fire` | Force-fire a reminder now (demo aid — real bookings are usually days out) |

### Editing tools into the graph (UI)

- **FR-14**: The edge inspector (see [voice-agent-builder-ui.md](voice-agent-builder-ui.md)) exposes
  a **Tool** picker, grouped by category, with "No tool" as the default. The catalog is loaded once
  on app mount from `GET /api/tools/catalog` (`ToolCatalogProvider` → `useToolCatalog()`); if the
  fetch fails, the picker degrades to an empty list (save validation still runs server-side).
  Picking a tool prefills the edge's `function`, `description`, and collected fields from that tool's
  defaults — via `frontend/src/lib/toolCatalog.ts` (types + `resolveToolPatch` helpers only; no
  duplicated tool list). Picking a tool always resets `tool_async` to `false`.
- **FR-15**: Once a tool is picked, a **"Run in the background"** checkbox appears, bound directly
  to `tool_async` — no separate tool selection for it, since it's a property of *how* the edge's own
  tool runs, not a different tool.
- **FR-16**: A tool-carrying edge is also visible directly on the canvas, not just when selected: its
  label carries a small icon badge — a wrench for a synchronous tool, a bolt for `tool_async` — via a
  custom React Flow edge component (`frontend/src/components/AgentEdge.tsx`) rendered through
  `EdgeLabelRenderer` (needed for a hoverable HTML badge; the default edge type only draws an SVG
  label). Hovering the badge shows a tooltip with the tool's name, whether it runs in the background,
  and its description — the same catalog metadata FR-14's picker uses, so the two stay in sync by
  construction. A plain routing edge (no `tool`) gets no badge.

### Copilot integration

- **FR-17**: `EdgeOut` (Build/Fix/Improve's structured-output shape, see
  [agent-copilot.md](agent-copilot.md)) carries an optional `tool` field constrained to the 6
  registry keys, and a `tool_async` bool, both passed through unchanged into the schema's
  `Edge.tool`/`Edge.tool_async`. Every `/chat` turn injects `available_tools: tool_catalog()` into
  the model's context JSON so replies and briefs only name real tool keys.
  `AGENT_DESIGN_RULES` documents when to use each tool, when `tool_async` is (and isn't)
  appropriate, forbids self-loops and invented tool names, and states that human-escalation and
  call-resilience are automatic and must never be modeled as nodes/edges by the Copilot.

### Worked example: Prosper Scheduler (Branched)

`backend/data/example_flow2.json`'s booking path wires three of the six tools onto its **existing**
edges — no new nodes, no new collected fields, so the existing tool-calling eval tests
(`backend/tests/test_tool_calling.py`) keep exercising the exact same function schemas they always
did; only what happens *after* the model calls them changed:

- `record_details` (`collect_details` → `verify_insurance`, collects `full_name`/`reason`): tool =
  `crm_lookup`, sync. As soon as we have a name, check if this is a returning caller.
- `record_insurance` (`verify_insurance` → `offer_times`, collects `has_insurance`/`member_id`): tool
  = `crm_create`, **async**. This is the case FR-6 describes: the model doesn't need to know the
  contact id to keep talking, so it's created in the background while the conversation continues
  through `offer_times`.
- `select_time` (`offer_times` → `confirm`, collects a fixed `slot` enum — no live slot lookup on
  this small, deliberately-simple menu): tool = `appointment_book`, sync. Falls into FR-10's label
  path (`book_label`, not `book_slot`) since there's no `slot_id`, and by now `crm_contact_id` is
  virtually always already in `flow_manager.state` (a couple of real conversational turns is ample
  time for an in-memory dummy write) — so the booking comes out linked to the CRM contact without
  the caller ever waiting on it.

## Acceptance Criteria

Covered by `backend/tests/test_tools.py` (fast, no API calls):

- [x] `appointment_lookup` returns only available slots; filtering by `service`/`date` narrows
      results.
- [x] `appointment_book` marks a slot unavailable, returns a booking id, and schedules a reminder
      when contact info is present; booking twice / an unknown slot raises `ValueError`.
- [x] `appointment_book` falls back to `book_label` when no `slot_id` is given, and links
      `crm_contact_id` from state either way.
- [x] `crm_lookup` returns `crm_found: true` + the contact for a seeded name, `false` for an unknown
      one; also resolves a caller given only a `full_name`.
- [x] `crm_create` creates a new contact, then reuses it (doesn't duplicate) on a second call for
      the same name; rejects with no name given.
- [x] `send_sms`/`send_email` record to the mock outbox and fall back to `state` for the recipient
      when the edge itself didn't collect it.
- [x] An `Edge.tool` naming an unknown key is rejected by `AgentBuilder._validate()`.
- [x] `tool_async: true` with no `tool` set is rejected.
- [x] A `tool_async` edge's handler returns before the tool resolves (no result in this turn's
      response), and `flow_manager.state` picks the result up shortly after.
- [x] An edge named `request_human_agent` or `confirm_human_transfer` is rejected.
- [x] A compiled non-terminal node's `functions` includes both global function names; a terminal
      node's does not.
- [x] `confirm_human_transfer`'s handler returns a `(result, node)` tuple whose node has
      `post_actions: [{"type": "end_conversation"}]` and no functions.
- [x] The Prosper Scheduler (Branched) example's three edges carry the tool/`tool_async` wiring
      described above, and a full simulated run (`record_details` → `record_insurance` →
      `select_time`) ends with a booking whose `crm_contact_id` matches the one the async
      `crm_create` produced.

Covered by `backend/tests/test_tool_calling.py` (LLM eval, real API calls) — confirms none of the
above changed what the model is actually offered or how it chooses:

- [x] All existing path-selection/argument-extraction assertions for the branched scheduler still
      hold — attaching a tool to an edge never changes that edge's declared function schema.
- [x] A caller asking to speak to a human when the current node also has its own, more specific
      transfer edge (`offer_times`'s `escalate_no_availability`) still calls that specific edge; it
      may *additionally* call the global `request_human_agent` (a harmless, redundant confirmation
      request that never gets acted on since the specific edge already ends the call) — both are
      reasonable given how literally the caller's phrasing matches the global escalation too.

Manual/browser:

- [x] Picking "Look up available appointment slots" in the edge inspector prefills function name,
      description, and collected fields; saving and test-calling exercises a real lookup.
- [x] Picking a tool reveals the "Run in the background" checkbox; toggling it round-trips through
      save/reload.
- [x] A tool-carrying edge shows a wrench (sync) or bolt (`tool_async`) badge on the canvas; a plain
      routing edge shows none; hovering the badge shows the tool's name/description tooltip.
- [x] Mid-call "I want to speak to a human" triggers exactly one confirmation before transferring;
      declining keeps the call in its current node.
- [x] Test-calling with a name not in the seeded CRM, then hanging up, results in a new contact at
      `GET /api/tools/crm`.

## Out of Scope / Deferred

- No LLM eval tests (`@pytest.mark.llm`) asserting the Copilot actually picks a tool, or the right
  sync/async setting, for relevant guidelines — would burn real API calls for a probabilistic
  assertion; deferred.
- No frontend view of bookings/CRM/outbox/reminders — the `/api/tools/*` endpoints exist for
  manual verification only.
- No configurable reminder offset (always "1 hour before") and no real clock-driven demo — the
  force-fire endpoint stands in for waiting out a real interval.
- No retry/backoff for the mock notification senders — they don't fail in this implementation.
- No way to *observe* whether a background (`tool_async`) call has finished from the UI or the call
  log — only a later tool handler reading `flow_manager.state` can tell.

## Related

- Code: `backend/tools/**`, `backend/routes/tools.py`, `backend/agent_builder/schema.py`,
  `backend/agent_builder/builder.py`, `backend/bot.py`, `backend/data/example_flow2.json`,
  `frontend/src/lib/toolCatalog.ts`, `frontend/src/components/EdgeInspector.tsx`,
  `frontend/src/components/AgentEdge.tsx`, `frontend/src/lib/agentGraph.ts`
- Tests: `backend/tests/test_tools.py`, `backend/tests/test_tool_catalog.py`,
  `backend/tests/test_tool_calling.py`
- Tradeoffs: [solution.md](../solution.md)

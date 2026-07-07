# Voice Agent Builder UI (Phase 1)

**Status:** Implemented. Source of truth for `frontend/` and the `/api/agents` + `/api/calls`
backend routes — update this spec before changing either.

## Overview

A React + React Flow UI for creating, editing, and test-calling agents defined by the contract in
[agent-schema-and-builder.md](agent-schema-and-builder.md). An agent is edited as a visual graph, not
raw JSON; every edit maps to a pure mutation of the same `AgentConfig` shape the backend validates.

## Goals

- Visual graph editing (nodes, edges, agent-level settings) with no hand-written JSON required.
- Safe editing: destructive or hard-to-undo actions (overwriting an agent's content, switching away
  from unsaved work, deleting the start node) are either blocked or require explicit confirmation.
- A working test call that always reflects the currently saved state of the agent being edited.
- Visibility into what a test call actually did, since the call itself runs outside this UI.

## Non-goals

- Persisting node position/layout — layout is always recomputed from graph structure
  (see "Canvas layout" below); dragging a node is a session-only convenience, not a saved property.
- Undo/redo, multi-user editing, authentication, or deleting an agent from the picker.
- Editing `pre_actions`/`post_actions` directly (schema-level escape hatches, not exposed in the UI).

## Requirements

### Agent management

Backed by `backend/store.py`'s `AgentStore` (in-memory, CRUD + one "active" pointer) via
`backend/routes/agents.py`:

| Method & path | Purpose |
| --- | --- |
| `GET /api/agents` | List agents as `{id, name}` |
| `GET /api/agents/{id}` | Full `AgentConfig`, re-validated via `AgentBuilder` before returning |
| `POST /api/agents` | Create from a full `AgentConfig` body; id is a slug of `name` (deduped if taken) |
| `PUT /api/agents/{id}` | Save edits; validated via `AgentBuilder` before persisting |
| `GET /api/agents/active` / `PUT /api/agents/active` | Which agent id the next test call runs |

- **FR-1**: Creating a new agent seeds it with `blankAgent()` — one node (`start`), `end: true`, no
  edges — and immediately selects it.
- **FR-2**: Switching the selected agent, or creating a new one, while the current agent has unsaved
  changes (`agent !== savedAgent`, deep-compared) must prompt **Discard / Save / Cancel**, not switch
  silently. Save persists the current agent via `PUT`, then proceeds to the originally-requested
  agent; Discard proceeds without saving; Cancel aborts and leaves the current agent untouched and
  selected.

### Canvas & layout

- **FR-3**: Node positions are computed by BFS depth from `initial_node` (`agentGraph.ts`), never
  read from or written to the saved `AgentConfig`.
- **FR-4**: Nodes are draggable. A manual drag position overrides the computed layout for that node
  only, held in frontend-only state. This override is cleared when the selected agent changes, or
  when the user clicks **Reorder** — there is no other way for a position to persist.
- **FR-5**: Hovering an edge visually raises it (thicker stroke, bolder label, drawn above whatever it
  overlaps) so overlapping edges/labels stay distinguishable without needing more canvas space.
- **FR-5a**: An edge carrying a tool (see [agent-tools.md](agent-tools.md)) shows a small badge on
  its label — no need to open the inspector just to see which edges do more than transition.

### Node editing

- **FR-6**: Selecting a node opens an inspector to edit: `name` (rename cascades to every edge
  `target` that pointed at the old name, and to `initial_node` if it was the renamed node — see
  `renameNode`), the first `task_messages` entry's `content`, and the `end` flag.
- **FR-7**: A node can be marked the start node ("Make this the start node"), which sets
  `initial_node`. The start node itself cannot be deleted.
- **FR-8**: Deleting a node removes it and cascades — every edge elsewhere in the graph that targeted
  it is removed too (`deleteNode`). No confirmation prompt (a not-yet-saved, reversible edit).
- **FR-9**: A node can gain a new outgoing edge either by dragging a connection between two nodes on
  the canvas, or via an "Add edge to…" picker in the node inspector — both produce the same edge
  shape (`addEdge`: function name auto-generated as `go_next`/`go_next_2`/…, empty description, no
  collected properties) and both open the edge inspector on the new edge immediately after.

### Edge editing

- **FR-10**: Selecting an edge opens an inspector to edit `function`, `target` (any other node in the
  agent), `description`, and a structured list of fields to collect (`name`, `type`
  `string`/`number`/`boolean`, `description`, `required`) — never raw JSON-schema editing.
- **FR-10a**: The edge inspector also has a **Tool** picker (grouped by category, "No tool" as the
  default) — see [agent-tools.md](agent-tools.md). Picking a tool prefills `function`,
  `description`, and the collected-fields list from that tool's defaults, without overwriting
  values already customized on the edge.
- **FR-11**: Deleting an edge removes only that edge from its source node.

### Agent-level settings

- **FR-12**: When nothing is selected, the inspector shows agent-level settings: `name`, `persona`,
  `model` (fixed choice list), `voice_id` (free text, ElevenLabs voice id).

### Test call

- **FR-13**: Clicking **Test call**: (a) saves the current agent if dirty, (b) marks it active via
  `PUT /api/agents/active`, (c) opens Pipecat's prebuilt client in a **new browser tab** pointed at
  `/client`. The tab is opened synchronously in the click handler (before the async save/activate
  calls) so it isn't blocked as a popup; it is deliberately **not** opened with `noopener`/
  `noreferrer`, since severing that reference would make it impossible to navigate the
  already-open tab to `/client` once setup finishes, and `/client` is first-party, trusted content.
  If the browser still blocks the tab, this is surfaced as an inline error rather than failing
  silently.
- **FR-14**: The backend resolves the *active* agent **per WebRTC connection**, not at process
  start (`bot.py`'s `bot()` reads `store.get_active_id()` inside the per-connection entry point).
  Consequence: a save takes effect on the very next test call with no backend restart.
- Explicitly not built as an embedded iframe — an iframe was tried first, but a Chrome
  Permissions-Policy interaction with Pipecat's own client bundle made it believe microphone access
  was already denied inside an iframe, so it never even prompted (see [solution.md](../solution.md)).

### Call log

- **FR-15**: Because the test call runs in a separate tab with no shared state, a "Call log" panel
  polls `GET /api/calls/log` (every 2s while open) and shows: the ordered list of nodes visited, which
  edge function led to each (`null` for the first/initial node), the fields collected at that step,
  and an accumulated `state` dict merging everything collected across the whole call.
- **FR-16**: `call_log.start(initial_node)` is called on `on_client_connected`, seeding the visit list
  with the initial node; `call_log.end()` is called on `on_client_disconnected`, marking `active:
  false` without clearing history. A new call (`start()` again) always resets history — only the
  current/most recent call's data is ever available, not a multi-call history.

## Acceptance Criteria

Verified by manual browser testing:

- [x] Renaming a node updates every edge `target` that pointed at the old name, and `initial_node` if
      it was the renamed node.
- [x] Deleting a node removes every edge elsewhere that targeted it.
- [x] The start node cannot be deleted; "Make this the start node" is hidden for the current start
      node and shown for every other node.
- [x] Dragging a node to a new position holds that position across unrelated edits to the same agent,
      and resets on switching agents or clicking Reorder.
- [x] Switching agents with unsaved changes shows the Discard/Save/Cancel prompt; Discard does not
      persist the change (confirmed via direct API read), Save does.
- [x] Test Call opens a new tab that lands on the Pipecat client for the currently active agent
      (confirmed the tab navigates to `/client`, not `about:blank`).
- [x] The Call Log panel shows an accurate path + collected fields for a simulated call exercising
      three nodes (verified directly against `AgentBuilder`'s handlers).
- [x] Requesting the call log before any backend restart / before any call has happened shows an
      explicit "no test call yet" state, and a genuine backend-unreachable error is shown distinctly
      from that empty state.

## Out of Scope / Deferred

- No manual reordering of sibling nodes within the same BFS depth (only free drag, not "insert
  before/after").
- No visual indication in the picker of which agent is currently *active* for test calls versus which
  is merely *open* for editing — they can differ (e.g. edit agent A, still test-call agent B) until
  Test Call is clicked.
- No agent deletion.

## Related

- Code: `frontend/src/**`, `backend/routes/agents.py`, `backend/store.py`, `backend/call_log.py`, `backend/bot.py`
- See also: [agent-tools.md](agent-tools.md) — the tool catalog behind FR-10a, and the call
  resilience processor added to `bot.py`'s pipeline.
- Tradeoffs: [solution.md](../solution.md) — "What's built" and "What's mocked, deferred, or cut"

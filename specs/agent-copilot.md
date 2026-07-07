# Agent Copilot (Phase 2)

**Status:** Implemented. Source of truth for `backend/routes/copilot.py` and the frontend Copilot panel —
update this spec before changing either.

## Overview

Automates the two manual workflows named in the brief: turning a client's natural-language
guidelines into a working agent ("Build"), and finding + fixing problems in a deployed agent from
call data ("Improve"). A third workflow — **Validate** — reviews the current draft on demand
(structural checks + LLM design review) and can hand findings into Improve the same way audited call
issues do. Build and Improve share a two-stage shape:

1. **Refine** — a multi-turn *refinement chat* (`/chat`) turns the engineer's rough input into a
   precise, self-contained `brief`, asking clarifying questions along the way. It generates nothing;
   it only shapes the brief. When the brief is complete the Copilot signals `ready` and shows a
   plain-language **plan** of what building will do.
2. **Generate & review** — approving the plan feeds the brief to generation (`/build` or `/improve`),
   which emits a **full candidate `AgentConfig`** plus a plain-English `explanation` of what it did.
   The frontend computes the structural diff itself, renders it on the canvas, and the user applies
   or discards it.

Nothing the Copilot produces bypasses the same `AgentBuilder` validation a human-edited save has to
pass (see [agent-schema-and-builder.md](agent-schema-and-builder.md)).

## Goals

- Reduce actual manual effort in both named workflows, not just add a chat window on top of the
  builder.
- Make issue *detection* — explicitly called out in the brief as its own burden — automatic, not just
  issue *resolution* — via Improve's call audit **and** Validate's draft review.
- Let the engineer **iterate on intent before committing** — refine a rough request into a good brief,
  see exactly what will happen, and only then generate — rather than one-shotting a prompt and hoping.
- Every proposal is reviewable before it does anything: refine, then plan-preview, then diff, then
  apply, then save.

## Non-goals

- Direct free-form graph editing by chat. The chat refines a *brief*; generation still emits a whole
  agent reviewed once as a diff — the chat never incrementally patches nodes/edges itself, so the
  "review a proposed diff" mechanic stays central.
- Server-side chat sessions. `/chat` is stateless — the frontend replays the full message history
  each turn; there is no conversation stored on the backend.
- Live call ingestion. Improve mode audits a fixed set of mocked transcripts
  (`backend/data/mock_calls.json`), not a real call-recording pipeline.
- A canned/fallback response path for LLM failures during a live demo — every Copilot action is a
  real OpenAI call with no pre-baked backup.

## Requirements

### Refinement chat (Build + Improve)

- **FR-0**: `POST /api/copilot/chat {mode: "build"|"improve", messages: [{role, content}], agent_id?,
  issue?}` → `{reply, brief, ready, plan: [str]}`. **Stateless**: the frontend replays the full
  message history each turn; no session is stored server-side. `reply` is the assistant's
  conversational message (may ask focused clarifying questions); `brief` is the accumulated,
  self-contained specification rewritten each turn and the *only* thing passed to generation; `ready`
  flips true once the brief is complete enough to build without guessing; `plan` is the
  plain-language, what-will-happen preview shown before generation (populated when `ready`).
  Improve requires `agent_id` (the current graph is added to the model instructions); an optional
  `issue` attaches that audited issue and its transcript as context. Every turn also receives
  `available_tools` from `tool_catalog()` in the context JSON (see [agent-tools.md](agent-tools.md)).
- **FR-0a** (UI): both modes present the refinement as a chat thread. Generation is not called until
  the engineer opens the **plan preview** (from a "Review & build" / "Review & apply" action) and
  confirms — "Keep iterating" returns to the chat. The engineer can always build before `ready`.
  **Restart chat** clears the thread (and any parent-held seed). On a failed `/chat` send, **Retry**
  resends the last user message and **Edit message** puts it back in the input for editing.

### Shared generation output contract (Build + Fix + Improve)

Every graph-generating endpoint (`/build`, `/fix`, `/improve`) has the LLM emit `GeneratedAgentOut`
via OpenAI's `responses.parse`: `{explanation: str, agent: AgentConfigOut}`. `explanation` is a
plain-English account of what was built/changed and why — narration for the reviewer, never the
source of truth for the diff (see FR-8). `agent` is converted 1:1 into the schema in
[agent-schema-and-builder.md](agent-schema-and-builder.md) (`_agent_config_to_dict`):

```
AgentConfigOut: name, persona, voice_id, model, initial_node, nodes: [NodeOut]
NodeOut: name, task_message: str, role_message?: str, end: bool, edges: [EdgeOut]
EdgeOut: function, description, target, collect: [EdgePropertyOut], tool?: ToolKey, tool_async?: bool
EdgePropertyOut: name, type ("string"|"number"|"boolean"), description, enum?: [str], required: bool
```

`collect` (a flat list) is converted into the schema's `properties` dict + `required` list at the
boundary — chosen because a flat list of named fields is a JSON-schema shape a model can reliably
emit with OpenAI structured outputs, whereas an arbitrary `{name: {...}}` dict is not well-suited to
strict structured-output mode.

Every generated node's `task_message` and rules are governed by a fixed instruction block
(`AGENT_DESIGN_RULES`) covering: replies must be speakable (no lists/emojis/markdown), `end`/`edges`
are mutually exclusive per node (mirrors FR-4 in the schema spec), `initial_node` and every edge
`target` must name a real node (no self-loops — add a new node for tool side effects instead),
edge `function` names must be unique within their node (mirrors FR-5), tools must use only keys from
the registry (never invented names), and to prefer 4–10 nodes.

### Build

- **FR-1**: `POST /api/copilot/build {guidelines: str}` → `{config: AgentConfig, explanation: str}`.
  Stateless — does not touch the store; the frontend decides whether/where to save the result.
  `guidelines` is the refined brief from `/chat` (or any raw guidelines string).
- **FR-2**: The returned `config` is validated with the same `AgentBuilder.from_dict` check used for
  human saves before the response is returned; a `ValueError` here becomes an HTTP 502, not a silently
  broken agent handed to the frontend.
- **FR-3** (UI): if the currently open agent already has real content (more than the one-node blank
  starter), the Build plan preview shows an overwrite warning before generation — Build always targets
  and would replace the *entire* open agent, there is no partial/merge mode.

### Improve

- **FR-4**: `GET /api/copilot/calls?agent_id=` → the mocked transcripts for that agent
  (`backend/data/mock_calls.json`, filtered by `agent_id`). Each transcript: `id`, `agent_id`,
  `caller_name`, `summary`, `transcript: [{speaker: "agent"|"caller", text}]`.
- **FR-5**: `POST /api/copilot/audit {agent_id}` → `{issues: [Issue]}`, one LLM call per invocation
  covering **all** of that agent's mock transcripts at once (not one call per transcript). Each
  `Issue`: `call_id`, `title`, `description`, `node_name` (which single node's behavior was at
  fault), `severity` (`low`/`medium`/`high`), `evidence_quote` (an exact line from the transcript).
  Calls with no real issue are skipped by instruction, not force-included.
- **FR-6** (UI): the audit runs automatically as soon as the Improve tab opens and mock calls exist
  for the agent — no manual "Scan" click required to see results. Detected issues render as a
  collapsible **inbox**; clicking one **seeds the refinement chat** with that issue as context
  (chat-first: the inbox provides detection, the chat provides iteration). A manual "Re-scan calls"
  action remains available (e.g., to re-check after applying a fix).
- **FR-7**: `POST /api/copilot/fix {agent_id, issue: Issue}` → `{config, explanation}`. The prompt
  includes the current agent, the specific issue, and that issue's full transcript, and instructs the
  model to return the **entire** corrected agent — copying every unrelated node/edge exactly — rather
  than a fragment or patch, so the frontend can diff old vs. new directly. Same `AgentBuilder`
  validation as Build applies before the response is returned. (Kept for the direct one-shot fix path
  and eval coverage; the chat-first UI routes through `/improve`.)
- **FR-7a**: `POST /api/copilot/improve {agent_id, brief: str, issue?: Issue}` → `{config,
  explanation}`. The Improve counterpart to `/build`: takes the refined brief from `/chat` (which may
  itself have started from an audited `issue` or from validation findings seeded as a chat message)
  and returns the whole corrected agent under the same whole-agent-edit instruction and validation
  as `/fix`.

### Validate

- **FR-10**: `POST /api/copilot/validate {config: AgentConfig}` → `{findings: [Finding]}`. Runs two
  passes over the draft in the request body (not the store): (1) deterministic structural checks via
  `validate_agent()` in `backend/agent_builder/validation.py`, tagged `source: "manual"`; (2) an LLM
  design review via `_llm_validate()`, tagged `source: "llm"` with a `suggestion` on each finding.
  LLM findings that duplicate a manual finding at the same node/edge are dropped (`dedup_llm_findings`).
  Malformed config → HTTP 400. Neither pass raises on a bad graph — reporting problems is the point.
- **FR-10a** (UI): see FR-5b in [voice-agent-builder-ui.md](voice-agent-builder-ui.md). Selected
  findings are formatted by `validationFindingsPrompt()` and passed to Improve as an `externalSeed`
  on `CopilotImproveTab` (cleared only after the seed message sends successfully).

### Diff computation

- **FR-8**: The diff shown to the user (`frontend/src/lib/agentDiff.ts`) is computed **client-side**
  by structurally comparing the current draft to the proposed config — the authoritative change set is
  never authored by the LLM. Per-node and per-edge status is one of `added` / `removed` / `modified` /
  `unchanged`; the "Exact changes" list in the review panel (`summarizeDiff`) is generated from that
  same comparison. The Copilot's `explanation` is rendered *alongside* it as a clearly-separated
  "What changed & why" narrative — readable, but subordinate to the structural diff.
- **FR-9**: Applying a proposal replaces the in-memory draft (`agent = preview`) but does **not**
  save it — a separate Save is still required, going through the same dirty-tracking and
  `PUT /api/agents/{id}` path as any manual edit.

## Acceptance Criteria

Covered by `backend/tests/test_copilot.py` (real OpenAI calls, `@pytest.mark.llm`),
`backend/tests/test_validation.py`, `backend/tests/test_validate_endpoint.py`, and
`backend/tests/test_prompts.py`, plus manual browser verification:

- [x] `build_agent` on a simple guidelines string returns a config that passes `AgentBuilder`
      validation and has more than one node, and a non-empty `explanation`.
- [x] `audit_calls` against `example_flow2`'s 4 seeded mock calls returns at least 3 issues, and the
      call engineered around "caller explicitly wants other times, not a transfer" (`call-2`) is
      attributed to `offer_times` specifically (correct node attribution, not just "found an issue").
- [x] `fix_issue` for that `call-2` issue returns a config that still validates, and either adds an
      edge to `offer_times` or adds a new node — i.e. a real, targeted change, not a no-op.
- [x] `copilot_chat` in build mode returns a non-empty `brief` and a coherent `reply`; a clearly
      complete request reaches `ready` with a non-empty `plan`.
- [x] `improve_agent` with a free-text brief (e.g. "let callers reschedule, not just book/cancel")
      against `example_flow2` returns a config that still validates and actually adds a path
      (new node or edge), with a non-empty `explanation`.
- [x] (Manual) The Build/Improve plan preview is shown before any generation call; "Keep iterating"
      makes no generation request. Build on an agent with content shows the overwrite warning there.
- [x] (Manual) Improve auto-runs the audit on opening the tab when mock calls exist, with no click
      required; clicking a detected issue seeds the chat with its context. An agent with zero mock
      calls shows an empty inbox and no audit call.
- [x] (Manual) Applying a proposed fix and saving persists it (confirmed via direct API read after
      Apply → Save in the browser).
- [x] `validate_agent_config` on a self-loop draft returns a manual "Self-loop edge" finding; mocked
      `_llm_validate` echoes are deduped and unrelated LLM findings are kept (`test_validate_endpoint.py`).
- [x] `dedup_llm_findings` keeps different issues on the same node but drops same-spot echoes
      (`test_validation.py`).
- [x] `AGENT_DESIGN_RULES` lists every `TOOL_REGISTRY` key and mentions `reservation_save` as an
      example of a forbidden invented tool (`test_prompts.py`).

## Out of Scope / Deferred

- No mock call data for agents other than `example_flow2` — Build-generated or hand-created agents
  show an empty Improve tab by design.
- No retry/backoff around the OpenAI calls; a transient failure surfaces as an inline error. The chat
  UI offers a manual **Retry** on failed sends, not automatic backoff.
- No persistence of past audit results — re-opening Improve or re-scanning always reflects the
  agent's *current* graph, not a history of past findings.

## Related

- Code: `backend/routes/copilot.py`, `backend/prompts.py` (`CHAT_BUILD_RULES` / `CHAT_IMPROVE_RULES` /
  `VALIDATION_RULES`), `backend/agent_builder/validation.py`, `backend/data/mock_calls.json`,
  `frontend/src/components/Copilot*.tsx` (incl. the shared `CopilotChat.tsx`),
  `frontend/src/components/ValidationPanel.tsx`, `frontend/src/components/DiffReviewPanel.tsx`,
  `frontend/src/lib/agentDiff.ts`, `frontend/src/lib/validationPrompt.ts`
- Tests: `backend/tests/test_copilot.py`, `backend/tests/test_validation.py`,
  `backend/tests/test_validate_endpoint.py`, `backend/tests/test_prompts.py`
- Tradeoffs: [solution.md](../solution.md) — "Why this Copilot design" and "Architecture"

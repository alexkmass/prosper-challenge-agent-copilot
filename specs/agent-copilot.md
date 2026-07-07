# Agent Copilot (Phase 2)

**Status:** Implemented. Source of truth for `backend/routes/copilot.py` and the frontend Copilot panel —
update this spec before changing either.

## Overview

Automates the two manual workflows named in the brief: turning a client's natural-language
guidelines into a working agent ("Build"), and finding + fixing problems in a deployed agent from
call data ("Improve"). Both modes converge on one mechanic: the LLM proposes a **full candidate
`AgentConfig`**, the frontend computes a diff against the current draft and renders it on the canvas,
and the user applies or discards it. Nothing the Copilot produces bypasses the same
`AgentBuilder` validation a human-edited save has to pass (see
[agent-schema-and-builder.md](agent-schema-and-builder.md)).

## Goals

- Reduce actual manual effort in both named workflows, not just add a chat window on top of the
  builder.
- Make issue *detection* — explicitly called out in the brief as its own burden — automatic, not just
  issue *resolution*.
- Every proposal is reviewable before it does anything: diff first, apply second, save third.

## Non-goals

- Open-ended multi-turn chat editing of the graph. Each Build or Improve action is one generation,
  reviewed once — not a conversation that incrementally patches the graph.
- Live call ingestion. Improve mode audits a fixed set of mocked transcripts
  (`backend/data/mock_calls.json`), not a real call-recording pipeline.
- A canned/fallback response path for LLM failures during a live demo — every Copilot action is a
  real OpenAI call with no pre-baked backup.

## Requirements

### Shared output contract (Build + Fix)

Both `/build` and `/fix` have the LLM emit the same structured shape (`AgentConfigOut`, via OpenAI's
`responses.parse` with `text_format=`), which is then converted 1:1 into the schema in
[agent-schema-and-builder.md](agent-schema-and-builder.md) (`_agent_config_to_dict`):

```
AgentConfigOut: name, persona, voice_id, model, initial_node, nodes: [NodeOut]
NodeOut: name, task_message: str, role_message?: str, end: bool, edges: [EdgeOut]
EdgeOut: function, description, target, collect: [EdgePropertyOut]
EdgePropertyOut: name, type ("string"|"number"|"boolean"), description, enum?: [str], required: bool
```

`collect` (a flat list) is converted into the schema's `properties` dict + `required` list at the
boundary — chosen because a flat list of named fields is a JSON-schema shape a model can reliably
emit with OpenAI structured outputs, whereas an arbitrary `{name: {...}}` dict is not well-suited to
strict structured-output mode.

Every generated node's `task_message` and rules are governed by a fixed instruction block
(`AGENT_DESIGN_RULES`) covering: replies must be speakable (no lists/emojis/markdown), `end`/`edges`
are mutually exclusive per node (mirrors FR-4 in the schema spec), `initial_node` and every edge
`target` must name a real node, edge `function` names must be unique within their node (mirrors FR-5),
and to prefer 4–10 nodes.

### Build

- **FR-1**: `POST /api/copilot/build {guidelines: str}` → `{config: AgentConfig}`. Stateless — does
  not touch the store; the frontend decides whether/where to save the result.
- **FR-2**: The returned `config` is validated with the same `AgentBuilder.from_dict` check used for
  human saves before the response is returned; a `ValueError` here becomes an HTTP 502, not a silently
  broken agent handed to the frontend.
- **FR-3** (UI): if the currently open agent already has real content (more than the one-node blank
  starter), Build shows a warning banner and requires an explicit "Generate anyway" confirmation
  before calling the endpoint — Build always targets and would replace the *entire* open agent, there
  is no partial/merge mode.

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
  for the agent — no manual "Scan" click required to see results. A manual "Re-scan calls" action
  remains available (e.g., to re-check after applying a fix).
- **FR-7**: `POST /api/copilot/fix {agent_id, issue: Issue}` → `{config: AgentConfig}`. The prompt
  includes the current agent, the specific issue, and that issue's full transcript, and instructs the
  model to return the **entire** corrected agent — copying every unrelated node/edge exactly — rather
  than a fragment or patch, so the frontend can diff old vs. new directly. Same `AgentBuilder`
  validation as Build applies before the response is returned.

### Diff computation

- **FR-8**: The diff shown to the user (`frontend/src/lib/agentDiff.ts`) is computed **client-side**
  by structurally comparing the current draft to the proposed config — not authored by the LLM as a
  separate `rationale`/`changes_summary` field. Per-node and per-edge status is one of `added` /
  `removed` / `modified` / `unchanged`; the change list shown in the review panel
  (`summarizeDiff`) is generated from that same comparison.
- **FR-9**: Applying a proposal replaces the in-memory draft (`agent = preview`) but does **not**
  save it — a separate Save is still required, going through the same dirty-tracking and
  `PUT /api/agents/{id}` path as any manual edit.

## Acceptance Criteria

Covered by `backend/tests/test_copilot.py` (real OpenAI calls, `@pytest.mark.llm`) plus manual
browser verification:

- [x] `build_agent` on a simple guidelines string returns a config that passes `AgentBuilder`
      validation and has more than one node.
- [x] `audit_calls` against `example_flow2`'s 4 seeded mock calls returns at least 3 issues, and the
      call engineered around "caller explicitly wants other times, not a transfer" (`call-2`) is
      attributed to `offer_times` specifically (correct node attribution, not just "found an issue").
- [x] `fix_issue` for that `call-2` issue returns a config that still validates, and either adds an
      edge to `offer_times` or adds a new node — i.e. a real, targeted change, not a no-op.
- [x] (Manual) Build on an agent that already has content shows the overwrite warning + confirmation
      before making the API call; Cancel makes no request.
- [x] (Manual) Improve auto-runs the audit on opening the tab when mock calls exist, with no click
      required; an agent with zero mock calls shows an empty state instead of an API call.
- [x] (Manual) Applying a proposed fix and saving persists it (confirmed via direct API read after
      Apply → Save in the browser).

## Out of Scope / Deferred

- No mock call data for agents other than `example_flow2` — Build-generated or hand-created agents
  show an empty Improve tab by design.
- No retry/backoff around the OpenAI calls; a transient failure surfaces as an inline error, not an
  automatic retry.
- No persistence of past audit results — re-opening Improve or re-scanning always reflects the
  agent's *current* graph, not a history of past findings.

## Related

- Code: `backend/routes/copilot.py`, `backend/data/mock_calls.json`, `frontend/src/components/Copilot*.tsx`,
  `frontend/src/lib/agentDiff.ts`
- Tests: `backend/tests/test_copilot.py`
- Tradeoffs: [solution.md](../solution.md) — "Why this Copilot design" and "Architecture"

# Decisions log

Running record of tradeoffs discussed and decisions made while building this, and why. See
[solution.md](solution.md) for the polished architecture writeup — this file is the working log.

## Scope framing

The challenge is explicit that Phase 2 (the Copilot) is "the heart of the challenge" and that
knowing what *not* to build is itself a signal. Given the ~8-12h budget, the plan was: build just
enough of Phase 1 to be a real, editable, testable graph builder, and spend the majority of the
creative effort on the Copilot's design.

## Phase 1

**Schema left unchanged.** `AgentConfig` / `Node` / `Edge` in `backend/agent_builder/schema.py`
were not touched. Edges stay Pipecat-native function-calling tools (a `function` name, a
`description` the LLM uses to decide when to call it, a `target` node, and JSON-schema
`properties`/`required` for anything to collect). Branching is just "multiple edges on one node."
This meant the Copilot never has to learn a second representation — it emits the same JSON a human
editing the UI produces.

**Node/edge layout is computed client-side and never persisted.** `agentGraph.ts` does a BFS-depth
layout from `initial_node` on every render. Tradeoff: manual node dragging doesn't stick — any
graph mutation (including typing in a task message) re-triggers the auto-layout. Accepted
deliberately: persisting `{x, y}` in the saved JSON would leak a UI concern into the agent contract
the backend and the Copilot both read/write, and manual rearrangement isn't in the requirements.

**Node identity = `name`, edge identity = `function` name (not array index).** The schema has no
separate id field. Renaming a node (`renameNode` in `agentMutations.ts`) cascades to every edge
`target` that pointed at it and to `initial_node`. Edges are looked up by `function` name within
their node rather than index, because indices shift under add/delete and would desync the
inspector's selection after any edit.

**Node deletion cascades silently** (drops edges that targeted the deleted node) rather than
blocking until the user manually clears references. This is a reversible, in-session, not-yet-saved
action, so the extra confirmation step wasn't worth the friction.

**Test call: embedded iframe, not a new tab.** Originally recommended a new tab (avoids WebRTC
mic-permission/CSS issues inside an iframe), but the user asked for an embedded iframe. This turned
out to be low-risk: `vite.config.ts` already proxies `/client` to the backend at the same origin
(`localhost:5173` → `localhost:7860`), so the iframe is same-origin and `allow="microphone"` works
without any cross-origin permission fight.

**Test call auto-saves first.** Clicking "Test call" saves the current draft (if dirty), marks it
active via `PUT /api/agents/active`, then opens the dialog — so the call always reflects what's on
screen instead of requiring a separate manual Save step first.

## Persistence model

**In-memory `AgentStore` behind an interface**, not a single mutable draft file. The user
specifically asked for "an interface that in the future would be used for the db but for much less
work" — `backend/store.py` defines an `AgentStore` protocol (`list`/`get`/`create`/`update`/
`get_active_id`/`set_active_id`) with `InMemoryAgentStore` as the only implementation, seeded at
import time from `example_flow.json` and `example_flow2.json`. Swapping in a real database later is
a one-class change; `api.py` and `bot.py` only ever talk to the interface.

**Key finding that shaped the "active agent" design:** Pipecat's dev runner invokes `bot()` fresh on
*every* new WebRTC connection (see `webrtc_connection_callback` in `pipecat/runner/run.py` —
`background_tasks.add_task(bot_module.bot, runner_args)`), not once at process start. So `bot.py`
resolves `store.get(store.get_active_id())` *inside* `bot()`, at connection time, instead of loading
a static file path at import time. Result: saved edits are live on the very next test call, with
**no backend restart**, and no hot-reload machinery needed.

## Phase 2 — Agent Copilot

**One mechanism, two entry points.** Both "Build" (guidelines → new agent) and "Improve" (flagged
issue → fix) do the same thing: the LLM returns a full candidate `AgentConfig` (not a patch/diff
format), the backend validates it with the same `AgentBuilder.from_dict` used for human saves, and
the frontend computes a diff against the current draft to render a colored overlay on the canvas
before anything is applied. This mirrors how coding agents work (propose a diff, human reviews,
human applies) but translated to a graph. Chose "LLM emits the full graph" over "LLM emits a
JSON-patch-style diff" because it's far more reliable for a model to reason about — it only has to
get the *end state* right, not track add/remove/modify operations against a mutable base, and it
lets the same generation path serve both Build and Improve.

**The diff is computed client-side, not LLM-authored.** `agentDiff.ts`'s `diffAgents`/
`summarizeDiff` compare old vs. new `AgentConfig` structurally — no `rationale`/`changes_summary`
field was added to the LLM's output schema. A generated diff is always accurate to what's actually
shown on the canvas; an LLM-authored description of its own diff could drift or be flatly wrong
about what it changed.

**Mock call transcripts, not live call recordings** (`backend/mock_calls.json`) — explicitly allowed
by the challenge ("we don't provide real call data — feel free to mock a few example calls"). Each
of the 4 transcripts against `example_flow2` was written to expose a *different class* of real
deployment-team problem, not just cosmetic issues:
- mid-flow intent switch with no escape edge (`call-1`, node `collect_details`)
- rigid options with no fallback when neither works (`call-2`, node `offer_times`)
- out-of-scope question answered instead of deferred (`call-3`, node `verify_insurance`)
- required field with no alternate lookup path (`call-4`, node `reschedule_lookup`)

The transcripts are static, but the audit and fix are **live LLM calls** against them every time —
nothing about the issues or fixes is canned.

**Live LLM only, no pre-baked fallback for the demo.** User's explicit choice over building a
safety-net path for API flakiness during a live review. Simpler to build and fully authentic; the
tradeoff is a bad completion or rate limit during the actual review has no fallback.

**Duplicate edge function names — a bug the schema doesn't catch.** Smoke-testing the Build endpoint
before wiring the frontend caught the LLM twice emitting two edges named `schedule_appointment` on
the same node (different targets). This is valid JSON against `schema.py` — `AgentBuilder` doesn't
reject it — but breaks Pipecat's ability to let the LLM disambiguate between branches at call time
(two identically-named tools). Fixed with a prompt rule *and* a server-side check
(`_validate_generated_config` in `copilot.py`) that rejects Copilot output with duplicate function
names per node before it's ever shown to the user, since prompt compliance alone isn't reliable
enough to trust for a generated contract that gets executed.

## UI

**shadcn/ui + Tailwind v4, default styling.** Initially misread "claudey" as a request for a
Claude.ai-styled visual theme; clarified it meant "make good use of Claude Code as a tool," not a
color palette. Kept shadcn's default (Nova/Radix) styling rather than building a custom theme —
no design-system work was in scope.

## Round 2 — usability feedback after the first demo pass

**Copilot Build now warns and confirms before overwriting.** Live testing surfaced the exact risk
flagged: Build was used on an already-populated agent and silently replaced its name and graph
(caught via `git`/API inspection, not a crash). Fixed by showing a banner in `CopilotBuildTab` when
the open agent has more than the blank starter's one node, and gating the actual generation call
behind an `AlertDialog` confirm ("Generate anyway"/"Cancel"). The diff-preview-before-save step was
already non-destructive, but the confirm avoids spending an LLM call and any confusion about intent
before the user even sees that step.

**Copilot Improve now auto-scans.** Detecting issues was framed from the start as "a burden" the
Copilot should remove — requiring a manual "Scan calls" click before showing anything undercut that.
`CopilotImproveTab` now runs the audit automatically as soon as mock calls are found for the agent
(no-op, no request, if there are none); a "Re-scan calls" button remains for re-running after a fix
is applied.

**"Set as start node" was an icon-only star with no visible label** — functionally it's a real
change (moves `initial_node`, which is why the layout jumps: layout is BFS-depth-from-start, so
changing the start necessarily reflows everything downstream). Rather than removing real
functionality, replaced the icon-only button with an explicit `"Make this the start node"` text
button, and the initial node now shows a plain-language `"The call starts here."` line instead of a
bare star.

**Edge labels overlapping** (parallel edges between sibling nodes at the same depth converging near
the same point) fixed two ways: widened `X_GAP`/`Y_GAP` in `agentGraph.ts` (80→160, 140→220) to give
labels more room in the first place, and added a hover state in `AgentCanvas.tsx` — the hovered edge
gets bumped to a higher `zIndex`, thicker stroke, and bolder label, and is moved to the end of the
render array so it draws on top of whatever it overlaps. Widening the gaps helps the common case;
the hover pop is the fallback for whenever labels still crowd (dense graphs, small screens).

**Nodes are now draggable with sticky positions**, addressing both "let me rearrange for clarity"
and "let me make room to insert a node." Manual drag positions are tracked in a `positions` map local
to `AgentCanvasInner` (`{nodeId: {x,y}}`), applied on top of the computed BFS layout, and reset
whenever the agent switches (new `agentId` prop) or the user clicks the new **Reorder** button next
to Add Node. This keeps the existing "layout is never persisted" rule intact — the override map is
pure frontend, in-memory, per-session state, not part of the saved `AgentConfig`.

**Test call: reverted from embedded iframe to a new tab.** First diagnosis (browser mic permission
denied for the origin) turned out to be a red herring specific to the automated test browser — the
user confirmed Chrome's mic permission for the site was Allow, and that visiting the backend
directly (`localhost:7860/client`) worked fine with no prompting issues at all. That isolated the
real cause to the iframe itself: inside `pipecat_ai_prebuilt`'s minified client bundle,
`navigator.permissions.query({name:'microphone'})` is checked first, and the code only proactively
calls `getUserMedia` (which is what actually surfaces the native prompt) when that query reports
`"prompt"`. Inside an iframe, Chrome's Permissions API can report `"denied"` for a feature even when
the top-level page has it granted — a known Permissions-Policy/iframe edge case — so Pipecat's code
took the "already denied" branch and rendered its blocked-mic UI without ever attempting the real
request. This matches the exact symptom: it never asked, because Pipecat's own code believed it
already knew the answer.

This is exactly the risk flagged back when the iframe was chosen over a new tab (see "Test call:
embedded iframe, not a new tab" above) — Chrome's iframe permission-policy behavior for
`getUserMedia`-adjacent APIs has had various inconsistencies across versions, and it isn't reliably
fixable from our side since the faulty check lives inside Pipecat's bundled client, not our code.
Given direct (non-iframed) access to the client is confirmed to work, reverted `TestCallDialog`'s
iframe embed to `window.open` in a new tab (`App.tsx`'s `handleTestCall`). To avoid popup-blocker
issues from the async save/set-active work before navigating, the tab is opened synchronously
inside the click handler and only navigated to `/client` once setup finishes — the standard pattern
for popup-safe async-gated tab opens. `TestCallDialog.tsx` was deleted as dead code.

**First cut of that fix opened the tab with `'noopener,noreferrer'`, which broke it again** — the
tab opened but sat on `about:blank` instead of navigating. `noopener` exists specifically to sever
the scripting connection between opener and the new window, so holding onto the returned handle to
later set `.location.href` is a documented anti-pattern (MDN: `window.open` can return `null` with
`noopener`; even when a handle comes back, using it to navigate afterward is inconsistent across
Chrome versions for the same reason). Since `/client` is our own trusted page rather than a
third-party URL, there's no reverse-tabnabbing risk here to justify `noopener` — removed it so the
held reference stays fully usable for the delayed navigation.

**Switching agents (or creating a new one) with unsaved changes now prompts Discard / Save /
Cancel.** `App.tsx` intercepts `AgentPicker`'s select/create actions through `requestSelectAgent`/
`requestCreateAgent`, which check `editor.dirty` and, if true, hold the intended action in
`pendingSwitch` state and show an `AlertDialog` instead of switching immediately. Save persists the
current agent, then continues to the originally-requested agent; Discard proceeds without saving;
Cancel aborts and leaves the user on the current agent untouched. Verified both paths end-to-end
(including confirming via direct API calls that Discard doesn't persist and Save does).

## Round 3 — a real crash found through testing, plus call visibility

**A test call disconnected right after answering "do you have insurance?"** — turned out to be a
genuine data bug, not Pipecat flakiness. The `verify_insurance` node in the saved agent had
`end: true` while also carrying an outgoing edge (`record_insurance` → `offer_times`). Per
`agent_builder/builder.py`'s `_make_node`, `end: true` unconditionally attaches an `end_conversation`
post-action, and Pipecat Flows executes a node's post-actions immediately on entering it (confirmed
by reading `pipecat_flows/manager.py`: `respond_immediately` defaults `true`, so post-actions run
right after queuing the node's first LLM turn, not after the user responds — the actual
`end_conversation` effect just takes a couple of pipeline-buffered seconds to visibly land, which is
why it looked like the user's "yes" triggered it). This is a self-contradictory state — a node marked
terminal that also has real, intended-to-be-reachable edges — that `AgentBuilder._validate()`
doesn't currently catch. Worth adding that check if this class of bug recurs (validate no node has
both `end: true` and non-empty `edges`), but out of scope for this pass since the user already fixed
the data directly via the node inspector's "Ends the call" toggle.

**Added a Call Log panel** so test-call outcomes are inspectable at all, since Test Call runs
Pipecat's client in its own tab with zero shared state with the builder. `backend/call_log.py` is a
small in-memory recorder (visits: which node, via which edge function, what was collected getting
there; plus an accumulated `state` dict across the whole call). Wired in via an optional
`on_transition` callback threaded through `AgentBuilder` (called from the existing edge handler in
`builder.py`) rather than duplicating transition logic elsewhere — `bot.py` starts/ends the log on
client connect/disconnect and passes `call_log.record_transition` in. Exposed as
`GET /api/calls/log`; the frontend (`CallLogSheet.tsx`) polls it every 2s while open. Verified the
whole chain by simulating the exact flow that had crashed (greeting → collect_details →
verify_insurance) directly against `AgentBuilder`'s handlers in Python — the log correctly showed
each node visited, which function led there, and the accumulated `full_name` / `reason` /
`has_insurance` / `member_id` fields, which is exactly what was asked for ("check the insurance id
was collected and the name and stuff").

## Round 4 — backend tests

**Researched what companies actually test for voice/conversational agents before designing the
suite** (per the user's explicit ask), rather than guessing. The consistent pattern across current
industry writeups (voice AI eval platforms, LLM agent eval surveys): a multi-layer split between
(1) audio/telephony infrastructure (STT/TTS quality, latency, interruptions, accents, packet loss)
and (2) the decision layer (tool-calling accuracy — right tool, right arguments, right number of
calls — and task/path completion), evaluated separately, plus a component-testing principle ("if the
agent has sub-components, unit-test each one in isolation; integration-test the combination"). The
user explicitly asked to weight this toward (2) and skip (1) — matches both the research and the
fact that we don't own the audio stack (Pipecat/ElevenLabs do).

**Two-tier suite, not one.** `test_agent_builder.py` is fast/deterministic/free (no API calls) —
the schema/compiler contract. `test_tool_calling.py` and `test_copilot.py` are real-OpenAI-call eval
tests marked `@pytest.mark.llm`, runnable separately (`make test-llm` / `make test-fast`) since
they're slower, cost tokens, and are inherently less deterministic than unit tests — conflating the
two tiers would make the fast tests slow and the eval tests' occasional flakiness look like a broken
build.

**Closed two real validation gaps found via this work**, both added to `AgentBuilder._validate()`
(not just Copilot's output-checking) since a human editing via the UI could trigger either just as
easily as the Copilot could:
- a node with `end: true` that also has outgoing edges (the exact bug that crashed the earlier test
  call) — now rejected at load time instead of silently ending every call that reaches it.
- duplicate edge function names within a node — previously only checked in `copilot.py`'s own
  post-generation validator; now checked once, for every agent, in the one place that already owns
  graph validation. `copilot.py`'s `_validate_generated_config` was simplified to just call
  `AgentBuilder.from_dict` now that the check lives there.

**Tool schemas under test come from Pipecat's own `OpenAILLMAdapter`, not a reimplementation.**
`tests/llm_helpers.py`'s `openai_tools_for_node` builds the exact `FunctionSchema` → OpenAI tool-dict
conversion Pipecat uses at runtime (`FlowsFunctionSchema.to_function_schema()` →
`ToolsSchema` → `OpenAILLMAdapter.to_provider_tools_format()`), rather than hand-rolling an
approximation. A hand-rolled version could silently drift from what the real agent sends and make a
test pass for the wrong reason.

**Scope: ~7 tool-calling evals + 3 Copilot evals + 8 unit tests (18 total), not a combinatorial
sweep.** Covers the 3-way branch at `greeting`, argument extraction + an enum-constrained argument at
`offer_times`, name/reason extraction plus a "don't call the tool on a half-answer" restraint check
at `collect_details`, and one test per Copilot action. Deliberately not covering every node or every
phrasing variant — matches the user's explicit "don't overdo it" instruction over exhaustive
edge-case coverage.

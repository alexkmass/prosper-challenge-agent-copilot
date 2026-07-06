---
name: pr-review
description: Use when asked to review this project's pull request, review the PR, review a branch against main and leave comments, or give an objective/independent review of the current branch's changes. Triggers on "/pr-review" or requests like "review the PR", "review this branch against origin main and leave comments in the PR". Posts a high-level, pragmatic review as real inline GitHub PR comments — correctness, architecture, performance, edge cases, and operational risk — not style or formatting.
---

# PR Review

You are reviewing this pull request as an **independent, objective reviewer** with no memory of how
it was built. Evaluate the code as it stands — not the process, not the intent. 

## Stance

Stay **high-level and pragmatic**. You're looking for things that would actually cause a problem —
not things you'd have written differently. Every finding should answer: *what breaks, and under what
conditions?* If you can't state a concrete failure scenario, it's not a finding — leave it out.

**Focus on:**
- **Correctness** — logic bugs, wrong assumptions, race conditions, error paths that don't actually
  handle the error, state that can desync.
- **Architecture** — is the structure sound for what this needs to do? Are abstractions justified by
  actual reuse/complexity, or introduced pre-emptively? Does new code fit how the rest of the
  codebase already solves similar problems, or does it quietly introduce a second way to do the same
  thing?
- **Performance** — real inefficiencies with a visible cost (N+1 calls, unnecessary re-renders,
  blocking I/O on a hot path, unbounded loops/recursion) — not micro-optimizations nobody would
  notice.
- **Edge cases** — inputs, states, or timings the code doesn't handle: empty/null/malformed input,
  concurrent access, partial failure, the first/last item in a collection, a network call that times
  out or returns something unexpected.
- **Operational risk** — things that would hurt in production or in a live demo: unhandled API
  failures, missing timeouts, secrets or credentials in code, injection risk, a dependency the code
  silently assumes will always behave, anything that fails loudly in dev but silently in prod (or
  vice versa).
- **Maintainability** — will someone else be able to change this safely later? Is complexity
  proportional to the problem it solves? Is there dead code, duplicated logic, or a config/behavior
  drift between two places that are supposed to agree?
- **Framework/tool best practices** — idiomatic use of the actual stack (see below). Flag places
  where the code fights the framework, misses a built-in the framework already provides, or violates
  a convention the framework relies on (not "I'd prefer a different pattern" — an actual convention
  violation with a real consequence).

**Do not comment on:** variable/function naming, formatting, whitespace, import ordering, comment
style, "I would have written this differently" with no functional difference, or any other
preference-level nit. If lint/type-check tooling would catch it, it doesn't need a human reviewer —
skip it.

## This stack's conventions, specifically

- **Backend (Python/FastAPI/Pydantic/Pipecat Flows)**: routes should stay thin and delegate to
  `agent_builder`/`store`/`copilot` modules; anything that mutates the agent graph should go through
  `AgentBuilder`'s validation, not bypass it; Pydantic models should be the boundary for
  request/response shapes, not raw dicts passed around internally; async handlers shouldn't block on
  sync I/O.
- **Frontend (React 19/React Flow/shadcn)**: state updates should be immutable (no direct mutation of
  `AgentConfig` objects); side effects belong in `useEffect`/event handlers, not render bodies; derived
  state should be computed, not duplicated into `useState`; API calls should handle rejection, not just
  the happy path.
- **Tests (pytest)**: unit tests (`test_agent_builder.py`) shouldn't need network access or an API
  key; eval tests (`@pytest.mark.llm`) are expected to be somewhat non-deterministic — flag a *flaky
  assertion structure* (over-strict exact-match on LLM output), not an occasional real failure.

## Process

1. **Find the PR.** `gh pr view --json number,headRefOid,baseRefName,url` for the current branch
   (or use a PR number if the user gave one). If there's no open PR for this branch, say so and stop
   — don't create one. Note the `headRefOid` (the PR's head commit SHA) — every inline comment is
   anchored to it.
2. **Get the diff.** `git fetch origin main` then `gh pr diff <number>` (or `git diff origin/main...HEAD`)
   for the full unified diff. Read it carefully enough to know exact file paths and line numbers —
   inline comments only land on lines that are actually part of the diff (added/modified lines on the
   "RIGHT" side; GitHub rejects a comment on a line outside any diff hunk).
3. **Check for your own prior comments.** `gh api repos/{owner}/{repo}/pulls/{number}/comments`
   (`{owner}`/`{repo}` are auto-filled by `gh` from the current repo — no lookup needed). If
   re-running against an updated push, don't repost a comment that's still substantively unresolved
   and already there. Only comment on what's new or still unaddressed.
4. **Read the intended design before reading the diff line-by-line.** This repo has
   [specs/](../../specs) (one per feature area: schema/builder, Voice Agent Builder UI, Agent
   Copilot) and [solution.md](../../solution.md) documenting what each piece is supposed to do and
   why. Read the relevant specs *first* so you're reviewing against the stated intent, not guessing
   it from the code.
5. **Check code against spec, and spec against code.** Two-way check: does the implementation
   actually satisfy the acceptance criteria in the relevant spec? And separately — has the code moved
   on from what the spec describes (new behavior, changed contract) without the spec being updated?
   A drifted spec is itself a finding.
6. **Read the diff for the failure-mode categories above.** Trace anything that touches shared state
   (`AgentStore`, `call_log`), validation (`AgentBuilder._validate`), or an external API call (OpenAI,
   ElevenLabs) especially carefully — that's where a bug has the most reach.
7. **Run what you can.** `make test-fast` always; `make test-llm` if `OPENAI_API_KEY` is available.
   A red test is a finding by itself — don't just note it, say what it implies about the diff.
8. **Don't fix anything.** This is a review, not a patch. Post findings as comments; let the author
   (or a follow-up session) decide what to act on.

## Output: post a real GitHub PR review

Submit **one** PR review (not scattered individual comments — one review event, all comments
attached) via the GitHub API:

1. Write the JSON payload to a scratch file, then submit it:
   ```
   gh api repos/{owner}/{repo}/pulls/{number}/reviews -X POST --input <path-to-payload.json>
   ```
2. Payload shape:
   ```json
   {
     "commit_id": "<headRefOid from step 1>",
     "event": "COMMENT",
     "body": "<one-line verdict + a short overview paragraph — anything that doesn't map to one specific line goes here, e.g. broad architecture concerns>",
     "comments": [
       { "path": "backend/copilot.py", "line": 42, "side": "RIGHT", "body": "<failure scenario, why it matters, optional one-line suggested direction>" }
     ]
   }
   ```
3. Every inline comment body should still follow the finding shape: **failure scenario** → **why it
   matters** → optional **suggested direction** in one line. No fluff, no praise-padding — if a
   comment doesn't change what the author does next, don't post it.
4. Overall verdict in the review `body`: **ready to merge**, **ready with minor concerns**, or
   **needs changes before merge**.
5. If a finding doesn't cleanly anchor to one line (a cross-cutting architecture concern, a missing
   test, a spec/code drift), put it in the review `body` as a bullet instead of forcing a line
   comment.
6. Use `event: "COMMENT"` (not `REQUEST_CHANGES` or `APPROVE`) — this skill flags issues, it doesn't
   gate the merge decision.
7. After submitting, reply in chat with the review's URL and a short plain-text summary of what got
   posted, so there's no need to alt-tab to GitHub to know what happened.

If there's nothing worth flagging in a category, don't manufacture something — just don't post a
comment for it. A short, high-signal review is the goal, not exhaustive coverage. It's fine to submit
a review with a short `body` and zero inline comments if the diff genuinely doesn't warrant any.

# Specs

Each file here is the source of truth for one feature area: what it does, the contracts it exposes,
and the acceptance criteria that define "done." They were written after the initial build (this
project moved fast during a take-home challenge), but from here on the rule is normal spec-driven
development: **change the spec first, then the code, then update the acceptance criteria** — don't
let the code and the spec drift apart.

| Spec | Covers |
| --- | --- |
| [agent-schema-and-builder.md](agent-schema-and-builder.md) | The declarative `AgentConfig`/`Node`/`Edge` contract and the compiler/validator (`AgentBuilder`) that turns it into a runnable Pipecat Flows graph. Foundational — everything else reads and writes this. |
| [voice-agent-builder-ui.md](voice-agent-builder-ui.md) | Phase 1: the React graph editor, agent CRUD, test calls, and the call log. |
| [agent-copilot.md](agent-copilot.md) | Phase 2: the Build and Improve Copilot modes. |

Each spec follows the same shape: Overview → Goals/Non-goals → Requirements (data contracts +
functional behavior + validation rules) → Acceptance Criteria → Out of Scope → Related (code, tests,
tradeoff notes). Acceptance criteria are written so they map directly onto either an automated test
in `backend/tests/` or a scripted manual check — if a criterion can't be checked one of those two
ways, it's not specific enough yet.

See [../solution.md](../solution.md) for the overall architecture writeup and the tradeoffs behind
these specs.

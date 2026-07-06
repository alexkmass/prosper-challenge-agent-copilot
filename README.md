# Prosper Challenge — Agent Composer

Voice AI for healthcare scheduling. An agent is a **graph of nodes** (Pipecat Flows), defined declaratively as JSON and compiled into a runnable voice pipeline.

- **Phase 1** — a UI to edit the node graph and place a test call.
- **Phase 2** — an Agent Copilot that generates and iterates on agents from natural language.

```
browser mic  ->  ElevenLabs STT  ->  OpenAI LLM  ->  ElevenLabs TTS  ->  browser
```

See [solution.md](solution.md) for the architecture writeup and tradeoffs, and [specs/](specs/) for the per-feature specs (the source of truth going forward — change the spec before the code).

## Quickstart

Requires **Python 3.11+** and [**uv**](https://docs.astral.sh/uv/getting-started/installation/) (uv will fetch a matching Python for you if needed). Run from the repo root:

```bash
make install         # uv sync — creates backend/.venv and installs from uv.lock
make run              # starts the backend on http://localhost:7860
make dev-frontend     # in a second terminal — starts the UI on http://localhost:5173
```

Copy `backend/.env.example` to `backend/.env` and fill in `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` first — the Copilot needs the OpenAI key too. Open `http://localhost:5173`, pick or create an agent, edit the graph, and hit **Test call** (mic access required) or **Copilot** to build/improve an agent from natural language. `Ctrl+C` to stop either process. (`make help` lists all targets.)

## Testing

```bash
make test-fast   # unit tests only — fast, deterministic, no API calls
make test-llm    # LLM eval tests — real OpenAI calls, needs OPENAI_API_KEY, ~20s
make test        # both
```

See `backend/tests/` — unit tests validate the agent schema/compiler; the eval tests check the
actual decision layer (does the LLM pick the right path, call the right tool, extract arguments
correctly) and the Copilot's build/audit/fix output. Nothing here drives real audio/telephony.

## Layout

| Path | Responsibility |
| --- | --- |
| `backend/bot.py` | The voice pipeline (WebRTC + ElevenLabs STT/TTS + OpenAI LLM). Resolves the store's *active* agent via `AgentBuilder` fresh on every connection and runs it — no graph logic lives here. |
| `backend/agent_builder/` | All agent-building code. `schema.py` = the declarative `AgentConfig` / `Node` / `Edge` contract; `builder.py` = `AgentBuilder`, which loads + validates the JSON and compiles it into a Pipecat Flows graph. |
| `backend/example_flow.json` / `example_flow2.json` | Two example agents **as data** — a linear clinic scheduler and a branched one (book/reschedule/cancel). Seed the store on startup; the Copilot generates/edits agents independently of these files. |
| `backend/store.py` | In-memory `AgentStore` (CRUD + active-agent pointer), seeded from the example flows. |
| `backend/call_log.py` | In-memory record of the current/last test call (nodes visited, fields collected) — surfaced in the UI since the test call runs in its own tab. |
| `backend/api.py` | `/api/agents` and `/api/calls/log` REST routes. |
| `backend/copilot.py` | `/api/copilot/*` routes — build from guidelines, audit mock calls, propose a fix. |
| `backend/mock_calls.json` | Mocked call transcripts the Copilot's Improve mode audits. |
| `backend/tests/` | Unit tests (schema/compiler validation) and LLM eval tests (tool-calling accuracy, Copilot correctness). |
| `frontend/` | The React + React Flow + shadcn/ui builder and Copilot panel. |
| `specs/` | Per-feature specs — requirements, contracts, and acceptance criteria. Source of truth going forward. |
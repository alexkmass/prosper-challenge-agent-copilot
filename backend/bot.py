#
# Voice pipeline — Prosper Product Engineer Challenge
#
# The runnable voice agent: WebRTC transport + ElevenLabs STT/TTS + OpenAI LLM,
# driven by a Pipecat Flows node graph. This file is generic — it loads the
# store's *active* agent and runs it. The Pipecat dev runner invokes bot() fresh
# on every new WebRTC connection, so resolving the active agent here (rather
# than once at import time) means edits saved from the UI take effect on the
# very next test call — no backend restart needed.
#
#   store.get(active_id)  ->  AgentBuilder  ->  Pipecat Flows graph  ->  FlowManager
#
# Run:  python bot.py   then open http://localhost:7860/client
#

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner
from pipecat_flows import FlowManager

from agent_builder import AgentBuilder
from call_recorder import CallRecorderObserver
from call_store import call_store
from store import store
from tools.crm_store import crm_store
from tools.handlers import resolve_full_name
from tools.resilience import CallResilienceProcessor

# Load .env next to this file, so the bot runs the same from the repo root or backend/.
load_dotenv(Path(__file__).parent / ".env", override=True)


transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


def _maybe_create_crm_contact(state: dict) -> None:
    """Create a CRM contact for a caller crm_lookup didn't find, using whatever the
    call collected. Deterministic post-call step — no LLM/tool call involved. Skipped
    if a `crm_create` tool edge already created (or reused) a contact mid-call.
    """
    if state.get("crm_found") is not False or state.get("crm_contact_id"):
        return
    first_name, last_name = resolve_full_name({}, state)
    if not first_name:
        return
    contact = crm_store.create_contact(
        first_name,
        last_name or "",
        insurance_id=state.get("insurance_id") or state.get("member_id"),
        phone_number=state.get("phone_number"),
        email=state.get("email"),
    )
    logger.info(f"Created CRM contact for new caller: {contact}")


async def run_bot(
    transport: BaseTransport, runner_args: RunnerArguments, builder: AgentBuilder, agent_id: str
) -> None:
    config = builder.config
    logger.info(f"Starting '{config.name}' with {len(config.nodes)} nodes")

    stt = ElevenLabsRealtimeSTTService(api_key=os.environ["ELEVENLABS_API_KEY"])
    tts = ElevenLabsTTSService(
        api_key=os.environ["ELEVENLABS_API_KEY"],
        settings=ElevenLabsTTSService.Settings(voice=config.voice_id),
    )
    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"], model=config.model)

    context = LLMContext()
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            # Catches non-fatal STT/LLM/TTS ErrorFrames pushed by the services above and
            # speaks a recovery line instead of letting the failure dead-end the turn.
            CallResilienceProcessor(),
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        # Mirrors transcript, node path, per-service timings, and errors into
        # call_store for the Call log UI — pure observer, doesn't touch frames.
        observers=[CallRecorderObserver(call_store)],
    )

    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=context_aggregator,
        worker=worker,
        transport=transport,
    )

    call_id: Optional[str] = None

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal call_id
        logger.info("Client connected — starting flow at initial node")
        call_id = call_store.start_call(agent_id, config.name, config.initial_node)
        await flow_manager.initialize(builder.build_initial_node())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        # Guaranteed to run once the pipeline stops, regardless of why — a clean
        # on_client_disconnected, a dropped connection, or an idle timeout all end up here,
        # so a call is never left "active" forever because its disconnect event never fired.
        if call_id is not None:
            state = call_store.get(call_id)["state"]
            call_store.end_call(call_id)
            _maybe_create_crm_contact(state)


async def bot(runner_args: RunnerArguments):
    """Entry point invoked by the Pipecat dev runner (and Pipecat Cloud).

    Invoked fresh per connection, so this always picks up whatever agent is
    currently marked active in the store — including edits saved seconds ago.
    """
    transport = await create_transport(runner_args, transport_params)
    active_id = store.get_active_id()
    builder = AgentBuilder.from_dict(store.get(active_id), on_transition=call_store.record_transition)
    await run_bot(transport, runner_args, builder, agent_id=active_id)


if __name__ == "__main__":
    from pipecat.runner.run import app, main

    from routes.agents import calls_router, router as agents_router
    from routes.copilot import router as copilot_router
    from routes.tools import router as tools_router

    app.include_router(agents_router)
    app.include_router(calls_router)
    app.include_router(copilot_router)
    app.include_router(tools_router)
    main()

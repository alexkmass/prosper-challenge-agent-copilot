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
from call_log import call_log
from store import store

# Load .env next to this file, so the bot runs the same from the repo root or backend/.
load_dotenv(Path(__file__).parent / ".env", override=True)


transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(
    transport: BaseTransport, runner_args: RunnerArguments, builder: AgentBuilder
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
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=context_aggregator,
        worker=worker,
        transport=transport,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected — starting flow at initial node")
        call_log.start(config.initial_node)
        await flow_manager.initialize(builder.build_initial_node())

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        call_log.end()
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Entry point invoked by the Pipecat dev runner (and Pipecat Cloud).

    Invoked fresh per connection, so this always picks up whatever agent is
    currently marked active in the store — including edits saved seconds ago.
    """
    transport = await create_transport(runner_args, transport_params)
    active_id = store.get_active_id()
    builder = AgentBuilder.from_dict(store.get(active_id), on_transition=call_log.record_transition)
    await run_bot(transport, runner_args, builder)


if __name__ == "__main__":
    from pipecat.runner.run import app, main

    from api import calls_router, router as agents_router
    from copilot import router as copilot_router

    app.include_router(agents_router)
    app.include_router(calls_router)
    app.include_router(copilot_router)
    main()

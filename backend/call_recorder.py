#
# CallRecorderObserver — watches every frame flowing through the pipeline and
# mirrors the parts worth keeping (transcript turns, per-service timings,
# token/character usage, errors) into the CallStore's active call.
#
# A pure observer rather than a FrameProcessor: it never touches push_frame,
# so it can't alter or drop pipeline frames by mistake (see BaseObserver).
#

from pipecat.frames.frames import (
    ErrorFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    TranscriptionFrame,
)
from pipecat.metrics.metrics import (
    LLMUsageMetricsData,
    MetricsData,
    ProcessingMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from call_store import CallStore


def _service_bucket(processor_name: str) -> str | None:
    """ElevenLabsRealtimeSTTService#0 / ElevenLabsTTSService#0 / OpenAILLMService#0 -> stt/tts/llm.

    Matched as suffixes on the name with its `#N` instance counter stripped, not raw substring
    checks — "ElevenLabsTTSService" lowercased contains "stt" as a substring (...lab-s-tt-service...),
    so a naive `"stt" in name` check misclassifies every TTS metric as STT.
    """
    base = processor_name.split("#", 1)[0].lower()
    if base.endswith("sttservice"):
        return "stt"
    if base.endswith("ttsservice"):
        return "tts"
    if base.endswith("llmservice"):
        return "llm"
    return None


class CallRecorderObserver(BaseObserver):
    """Feeds `store`'s active call from frames flowing through the pipeline."""

    def __init__(self, store: CallStore) -> None:
        super().__init__()
        self._store = store
        self._frames_seen: set[int] = set()
        self._llm_buffer: list[str] = []
        self._in_llm_turn = False

    async def on_push_frame(self, data: FramePushed) -> None:
        frame = data.frame
        # Same frame object is pushed once per processor-to-processor hop; only
        # act on it the first time it's seen (mirrors MetricsLogObserver).
        if frame.id in self._frames_seen:
            return
        self._frames_seen.add(frame.id)

        if isinstance(frame, TranscriptionFrame):
            self._store.add_transcript_entry("caller", frame.text)
        elif isinstance(frame, LLMFullResponseStartFrame):
            self._in_llm_turn = True
            self._llm_buffer = []
        elif isinstance(frame, LLMTextFrame) and self._in_llm_turn:
            self._llm_buffer.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self._in_llm_turn = False
            text = "".join(self._llm_buffer).strip()
            self._llm_buffer = []
            if text:
                self._store.add_transcript_entry("agent", text)
        elif isinstance(frame, ErrorFrame):
            processor_name = getattr(frame.processor, "name", None)
            self._store.add_error(frame.error, frame.fatal, processor_name)
        elif isinstance(frame, MetricsFrame):
            for metrics_data in frame.data:
                self._record_metric(metrics_data)

    def _record_metric(self, metrics_data: MetricsData) -> None:
        bucket = _service_bucket(metrics_data.processor)
        if bucket is None:
            return
        if isinstance(metrics_data, TTFBMetricsData):
            self._store.add_metric(bucket, "ttfb", metrics_data.processor, metrics_data.value, metrics_data.model)
        elif isinstance(metrics_data, ProcessingMetricsData):
            self._store.add_metric(
                bucket, "processing", metrics_data.processor, metrics_data.value, metrics_data.model
            )
        elif isinstance(metrics_data, LLMUsageMetricsData):
            self._store.add_metric(
                bucket, "usage_tokens", metrics_data.processor, metrics_data.value.model_dump(), metrics_data.model
            )
        elif isinstance(metrics_data, TTSUsageMetricsData):
            self._store.add_metric(
                bucket, "usage_chars", metrics_data.processor, metrics_data.value, metrics_data.model
            )

"""
Fast, deterministic unit tests for CallRecorderObserver's metric bucketing.

Real regression: `ElevenLabsTTSService` lowercased is "elevenlabsttsservice", which contains
"stt" as a substring (...lab-s-tt-service...) — a naive `"stt" in name` check therefore
misclassified every TTS metric as STT, leaving the Stats panel's TTS card permanently empty.
"""

from call_recorder import _service_bucket


def test_tts_service_is_not_misclassified_as_stt():
    assert _service_bucket("ElevenLabsTTSService#0") == "tts"
    assert _service_bucket("ElevenLabsTTSService#1") == "tts"


def test_stt_service_is_classified_as_stt():
    assert _service_bucket("ElevenLabsRealtimeSTTService#0") == "stt"


def test_llm_service_is_classified_as_llm():
    assert _service_bucket("OpenAILLMService#0") == "llm"


def test_unrecognized_processor_returns_none():
    assert _service_bucket("SomeOtherProcessor#0") is None

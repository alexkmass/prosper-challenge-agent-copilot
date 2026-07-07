"""
Fast, deterministic unit tests for the in-memory CallStore — no LLM calls, no
pipeline. Covers the multi-call lifecycle, per-service stats aggregation, and
the "no active call" no-ops that let call_recorder.py fire without guarding
every call site.
"""

from call_store import InMemoryCallStore, summarize_stats


def test_start_call_creates_active_record_with_initial_visit():
    store = InMemoryCallStore()
    call_id = store.start_call("example_flow2", "Prosper Scheduler", "greeting")

    assert store.get_active_id() == call_id
    record = store.get(call_id)
    assert record["status"] == "active"
    assert record["visits"] == [{"at": record["visits"][0]["at"], "node": "greeting", "via_function": None, "collected": {}}]


def test_writes_target_the_active_call():
    store = InMemoryCallStore()
    call_id = store.start_call("example_flow2", "Prosper Scheduler", "greeting")

    store.record_transition("collect_details", "collect_details", {"full_name": "Maria Alvarez"})
    store.add_transcript_entry("caller", "Hi, I'd like to book an appointment.")
    store.add_transcript_entry("agent", "Sure, what's your name?")

    record = store.get(call_id)
    assert record["state"] == {"full_name": "Maria Alvarez"}
    assert [t["speaker"] for t in record["transcript"]] == ["caller", "agent"]
    assert record["stats"]["message_count"] == 2


def test_blank_transcript_entries_are_dropped():
    store = InMemoryCallStore()
    store.start_call("example_flow2", "Prosper Scheduler", "greeting")

    store.add_transcript_entry("agent", "   ")
    store.add_transcript_entry("caller", "")

    record = store.get(store.get_active_id())
    assert record["transcript"] == []
    assert record["stats"]["message_count"] == 0


def test_end_call_clears_active_id_and_freezes_status():
    store = InMemoryCallStore()
    call_id = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    store.end_call(call_id)

    assert store.get_active_id() is None
    record = store.get(call_id)
    assert record["status"] == "ended"
    assert record["ended_at"] is not None


def test_start_call_force_ends_a_still_active_previous_call():
    """Simulates a dropped connection: on_client_disconnected never fires, so the old call
    would otherwise stay "active" forever. Starting a new call must not leave it stranded."""
    store = InMemoryCallStore()
    orphaned = store.start_call("example_flow2", "Prosper Scheduler", "greeting")

    new_call = store.start_call("example_flow2", "Prosper Scheduler", "greeting")

    assert store.get_active_id() == new_call
    orphaned_record = store.get(orphaned)
    assert orphaned_record["status"] == "ended"
    assert orphaned_record["ended_at"] is not None


def test_end_call_on_already_superseded_call_does_not_touch_new_active_call():
    """A late-firing on_client_disconnected (or a finally-block cleanup) for a call that's
    already been force-ended by a newer start_call must be a no-op, not clobber the new call."""
    store = InMemoryCallStore()
    old_call = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    new_call = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    already_ended_at = store.get(old_call)["ended_at"]

    store.end_call(old_call)  # late/duplicate cleanup call for the superseded call

    assert store.get_active_id() == new_call
    assert store.get(new_call)["status"] == "active"
    assert store.get(old_call)["ended_at"] == already_ended_at


def test_writes_after_end_are_silently_dropped():
    """call_recorder observes every frame regardless of call state; it must never raise."""
    store = InMemoryCallStore()
    call_id = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    store.end_call(call_id)

    store.add_transcript_entry("caller", "still talking after hangup")
    store.record_transition("fn", "node", {"x": 1})
    store.add_metric("llm", "ttfb", "OpenAILLMService#0", 0.1)
    store.add_error("boom", False, "proc")


def test_list_is_most_recent_first_and_summarizes():
    store = InMemoryCallStore()
    first = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    store.record_transition("collect_details", "collect_details", {"full_name": "Maria Alvarez"})
    store.end_call(first)
    second = store.start_call("example_flow2", "Prosper Scheduler", "greeting")
    store.end_call(second)

    ids = [c["id"] for c in store.list()]
    assert ids == [second, first]

    first_summary = next(c for c in store.list() if c["id"] == first)
    assert first_summary["caller_name"] == "Maria Alvarez"
    assert first_summary["status"] == "ended"


def test_get_unknown_call_raises():
    import pytest

    from call_store import CallNotFoundError

    store = InMemoryCallStore()
    with pytest.raises(CallNotFoundError):
        store.get("does-not-exist")


def test_max_calls_prunes_oldest_but_keeps_active():
    store = InMemoryCallStore(max_calls=2)
    a = store.start_call("agent", "Agent", "n")
    store.end_call(a)
    b = store.start_call("agent", "Agent", "n")
    store.end_call(b)
    c = store.start_call("agent", "Agent", "n")  # still active — must survive pruning

    ids = {call["id"] for call in store.list()}
    assert a not in ids
    assert b in ids
    assert c in ids


def test_summarize_stats_aggregates_per_bucket():
    stats = {
        "message_count": 4,
        "llm": [
            {"kind": "ttfb", "value": 0.2},
            {"kind": "ttfb", "value": 0.4},
            {"kind": "processing", "value": 1.0},
            {"kind": "processing", "value": 1.5},
            {"kind": "usage_tokens", "value": {"total_tokens": 120}},
            {"kind": "usage_tokens", "value": {"total_tokens": 80}},
        ],
        "stt": [{"kind": "processing", "value": 0.05}],
        "tts": [{"kind": "usage_chars", "value": 42}],
        "errors": [
            {"error": "STT timeout", "fatal": False},
            {"error": "LLM connection reset", "fatal": True},
        ],
    }

    summary = summarize_stats(stats)

    assert summary["message_count"] == 4
    assert summary["error_count"] == 2
    assert summary["fatal_error_count"] == 1
    assert summary["llm"]["call_count"] == 2
    assert summary["llm"]["avg_ttfb_secs"] == 0.3
    assert summary["llm"]["total_processing_secs"] == 2.5
    assert summary["llm"]["total_tokens"] == 200
    assert summary["stt"]["total_processing_secs"] == 0.05
    assert summary["tts"]["total_tts_characters"] == 42


def test_summarize_stats_empty_bucket_reports_none_not_zero():
    summary = summarize_stats({"message_count": 0, "llm": [], "stt": [], "tts": [], "errors": []})

    assert summary["llm"]["call_count"] == 0
    assert summary["llm"]["avg_ttfb_secs"] is None
    assert summary["llm"]["total_processing_secs"] is None
    assert summary["llm"]["total_tokens"] is None

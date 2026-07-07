#
# In-memory store of test calls — one record per call, covering node path,
# transcript, collected state, and per-service performance stats (LLM/STT/TTS
# timings, token/character usage, errors).
#
# Kept behind a small interface (CallStore) so a real database can replace
# InMemoryCallStore later without touching api.py, bot.py, or call_recorder.py
# — same pattern as store.py's AgentStore.
#
# Most "write" methods act on whichever call is currently active, mirroring how a live test
# call has exactly one in-flight call at a time (one browser tab, no concurrent calls).
# `end_call` takes an explicit id instead, so a caller that's guaranteeing cleanup (e.g. a
# `finally` block after the pipeline stops, regardless of why) can safely close out *its own*
# call even if a newer one has since become active — and `start_call` uses the same explicit
# call to force-end any still-"active" call it's about to supersede, in case that call's own
# cleanup never ran (dropped connection, tab closed without a clean disconnect).
#

import time
import uuid
from typing import Literal, Optional, Protocol

TranscriptSpeaker = Literal["caller", "agent"]
MetricBucket = Literal["llm", "stt", "tts"]

_STAT_BUCKETS: tuple[MetricBucket, ...] = ("llm", "stt", "tts")


class CallNotFoundError(KeyError):
    """Raised when a call id isn't in the store."""


class CallStore(Protocol):
    """Everything api.py, bot.py, and call_recorder.py need — swap the impl freely."""

    def start_call(self, agent_id: str, agent_name: str, initial_node: str) -> str: ...
    def end_call(self, call_id: str) -> None: ...
    def get_active_id(self) -> Optional[str]: ...
    def record_transition(self, function: str, target: str, collected: dict) -> None: ...
    def add_transcript_entry(self, speaker: TranscriptSpeaker, text: str) -> None: ...
    def add_metric(
        self, bucket: MetricBucket, kind: str, processor: str, value: object, model: Optional[str] = None
    ) -> None: ...
    def add_error(self, error: str, fatal: bool, processor: Optional[str]) -> None: ...
    def list(self) -> list[dict]: ...
    def get(self, call_id: str) -> dict: ...


def _new_stats() -> dict:
    return {"message_count": 0, "llm": [], "stt": [], "tts": [], "errors": []}


def summarize_stats(stats: dict) -> dict:
    """Roll the raw per-event stats up into the aggregates the UI displays."""

    def _values(entries: list[dict], kind: str) -> list[float]:
        return [e["value"] for e in entries if e["kind"] == kind and isinstance(e["value"], (int, float))]

    def _bucket_summary(bucket: str) -> dict:
        entries = stats[bucket]
        processing = _values(entries, "processing")
        ttfb = _values(entries, "ttfb")
        usage_chars = _values(entries, "usage_chars")
        token_usages = [e["value"] for e in entries if e["kind"] == "usage_tokens" and isinstance(e["value"], dict)]
        total_tokens = sum(u.get("total_tokens", 0) for u in token_usages)
        return {
            "call_count": max(len(processing), len(ttfb)),
            "avg_ttfb_secs": round(sum(ttfb) / len(ttfb), 3) if ttfb else None,
            "total_processing_secs": round(sum(processing), 3) if processing else None,
            "total_tokens": total_tokens or None,
            "total_tts_characters": sum(usage_chars) or None,
        }

    errors = stats["errors"]
    return {
        "message_count": stats["message_count"],
        "error_count": len(errors),
        "fatal_error_count": sum(1 for e in errors if e["fatal"]),
        **{bucket: _bucket_summary(bucket) for bucket in _STAT_BUCKETS},
    }


class InMemoryCallStore:
    """Dict-backed CallStore. Fine for a single-process demo; not persisted."""

    def __init__(self, max_calls: int = 200) -> None:
        self._calls: dict[str, dict] = {}
        self._order: list[str] = []  # insertion order, oldest first
        self._active_id: Optional[str] = None
        self._max_calls = max_calls

    # ---- lifecycle -----------------------------------------------------

    def start_call(self, agent_id: str, agent_name: str, initial_node: str) -> str:
        # A prior call whose disconnect was never observed (dropped connection, tab closed
        # without a clean handshake) would otherwise stay "active" forever. Only one test call
        # runs at a time, so a new one starting means the old one is definitely over.
        if self._active_id is not None:
            self.end_call(self._active_id)

        call_id = uuid.uuid4().hex[:12]
        now = time.time()
        self._calls[call_id] = {
            "id": call_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "status": "active",
            "started_at": now,
            "ended_at": None,
            "visits": [{"at": now, "node": initial_node, "via_function": None, "collected": {}}],
            "state": {},
            "transcript": [],
            "stats": _new_stats(),
        }
        self._order.append(call_id)
        self._active_id = call_id
        self._prune()
        return call_id

    def end_call(self, call_id: str) -> None:
        record = self._calls.get(call_id)
        if record is None or record["status"] == "ended":
            return
        record["status"] = "ended"
        record["ended_at"] = time.time()
        if self._active_id == call_id:
            self._active_id = None

    def get_active_id(self) -> Optional[str]:
        return self._active_id

    def _active_record(self) -> Optional[dict]:
        if self._active_id is None:
            return None
        return self._calls.get(self._active_id)

    def _prune(self) -> None:
        while len(self._order) > self._max_calls:
            oldest = self._order.pop(0)
            if oldest != self._active_id:
                self._calls.pop(oldest, None)

    # ---- writes (always target the active call) ------------------------

    def record_transition(self, function: str, target: str, collected: dict) -> None:
        record = self._active_record()
        if record is None:
            return
        record["state"].update(collected)
        record["visits"].append(
            {"at": time.time(), "node": target, "via_function": function, "collected": collected}
        )

    def add_transcript_entry(self, speaker: TranscriptSpeaker, text: str) -> None:
        if not text or not text.strip():
            return
        record = self._active_record()
        if record is None:
            return
        record["transcript"].append({"at": time.time(), "speaker": speaker, "text": text})
        record["stats"]["message_count"] += 1

    def add_metric(
        self, bucket: MetricBucket, kind: str, processor: str, value: object, model: Optional[str] = None
    ) -> None:
        record = self._active_record()
        if record is None:
            return
        record["stats"][bucket].append(
            {"at": time.time(), "kind": kind, "processor": processor, "model": model, "value": value}
        )

    def add_error(self, error: str, fatal: bool, processor: Optional[str]) -> None:
        record = self._active_record()
        if record is None:
            return
        record["stats"]["errors"].append(
            {"at": time.time(), "error": error, "fatal": fatal, "processor": processor}
        )

    # ---- reads -----------------------------------------------------------

    def list(self) -> list[dict]:
        return [self._summarize(self._calls[cid]) for cid in reversed(self._order) if cid in self._calls]

    def get(self, call_id: str) -> dict:
        record = self._require(call_id)
        return {**record, "stats_summary": summarize_stats(record["stats"])}

    def _summarize(self, record: dict) -> dict:
        ended_at = record["ended_at"] or time.time()
        return {
            "id": record["id"],
            "agent_id": record["agent_id"],
            "agent_name": record["agent_name"],
            "status": record["status"],
            "started_at": record["started_at"],
            "ended_at": record["ended_at"],
            "duration_secs": round(ended_at - record["started_at"], 1),
            "caller_name": record["state"].get("full_name"),
            "message_count": record["stats"]["message_count"],
            "error_count": len(record["stats"]["errors"]),
        }

    def _require(self, call_id: str) -> dict:
        try:
            return self._calls[call_id]
        except KeyError:
            raise CallNotFoundError(call_id) from None


call_store = InMemoryCallStore()

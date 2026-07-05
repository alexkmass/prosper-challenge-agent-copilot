#
# In-memory record of the current/most recent test call.
#
# Test calls run in their own browser tab (Pipecat's prebuilt client) with no
# shared state with the builder UI, so there's otherwise no way to see what
# the agent actually collected — this gives the UI something to poll.
#

import time


class CallLog:
    """Single-call, single-process log. Fine for a local dev tool; not persisted."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._visits: list[dict] = []
        self._state: dict = {}
        self._active = False

    def start(self, initial_node: str) -> None:
        self.reset()
        self._active = True
        self._visits.append({"at": time.time(), "node": initial_node, "via_function": None, "collected": {}})

    def record_transition(self, function: str, target: str, collected: dict) -> None:
        self._state.update(collected)
        self._visits.append(
            {"at": time.time(), "node": target, "via_function": function, "collected": collected}
        )

    def end(self) -> None:
        self._active = False

    def snapshot(self) -> dict:
        return {"active": self._active, "visits": self._visits, "state": self._state}


call_log = CallLog()

#
# In-memory reminder scheduler — used by `appointment_book` to queue a
# "1 hour before" reminder, delivered through the same mock senders the
# `send_sms`/`send_email` tools use.
#
# A background asyncio loop polls for due reminders, but demo bookings are
# usually days out, so `fire()` (exposed via POST /api/tools/reminders/{id}/fire)
# lets one be sent on demand instead of waiting out the real interval.
#

import asyncio
import uuid
from datetime import datetime
from typing import Literal, Optional, Protocol

from loguru import logger

from .notifications import EmailSender, SmsSender, email_sender, sms_sender

POLL_INTERVAL_SECONDS = 5
Channel = Literal["sms", "email"]


class ReminderScheduler(Protocol):
    def schedule(self, run_at: datetime, channel: Channel, to: str, message: str) -> dict: ...
    def list(self) -> list[dict]: ...
    def fire(self, reminder_id: str) -> dict: ...


class InMemoryReminderScheduler:
    """Dict-backed ReminderScheduler with a lazily-started background poll loop."""

    def __init__(self, sms: SmsSender, email: EmailSender) -> None:
        self._sms = sms
        self._email = email
        self._reminders: dict[str, dict] = {}
        self._loop_task: Optional[asyncio.Task] = None

    def schedule(self, run_at: datetime, channel: Channel, to: str, message: str) -> dict:
        reminder_id = f"reminder-{uuid.uuid4().hex[:8]}"
        reminder = {
            "id": reminder_id,
            "run_at": run_at.isoformat(),
            "channel": channel,
            "to": to,
            "message": message,
            "status": "pending",
        }
        self._reminders[reminder_id] = reminder
        self._ensure_loop_running()
        return dict(reminder)

    def list(self) -> list[dict]:
        return [dict(r) for r in self._reminders.values()]

    def fire(self, reminder_id: str) -> dict:
        reminder = self._reminders.get(reminder_id)
        if reminder is None:
            raise ValueError(f"No reminder called '{reminder_id}'.")
        if reminder["status"] != "sent":
            self._send(reminder)
        return dict(reminder)

    def _send(self, reminder: dict) -> None:
        if reminder["channel"] == "sms":
            self._sms.send(reminder["to"], reminder["message"])
        else:
            self._email.send(reminder["to"], "Appointment reminder", reminder["message"])
        reminder["status"] = "sent"

    def _ensure_loop_running(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no event loop yet (e.g. a sync unit test) — fire() still works manually
        self._loop_task = loop.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        while True:
            now = datetime.now()
            for reminder in self._reminders.values():
                if reminder["status"] == "pending" and datetime.fromisoformat(reminder["run_at"]) <= now:
                    try:
                        self._send(reminder)
                    except Exception as e:
                        logger.error(f"Failed to send reminder {reminder['id']}: {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


reminder_scheduler = InMemoryReminderScheduler(sms_sender, email_sender)

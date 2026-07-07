#
# Mock SMS/email senders — the backing "gateway" for the `send_sms` /
# `send_email` tools and for reminders (see scheduler.py). Real send calls are
# swapped in later by implementing these two Protocols against an actual
# SMS/email provider; nothing else in tools/ or agent_builder/ would change.
#

import time
import uuid
from typing import Optional, Protocol

from loguru import logger


class SmsSender(Protocol):
    def send(self, to: str, message: str) -> dict: ...
    def outbox(self) -> list[dict]: ...


class EmailSender(Protocol):
    def send(self, to: str, subject: str, message: str) -> dict: ...
    def outbox(self) -> list[dict]: ...


class MockSmsSender:
    """Records every 'sent' text instead of calling a real SMS gateway."""

    def __init__(self) -> None:
        self._outbox: list[dict] = []

    def send(self, to: str, message: str) -> dict:
        record = {
            "id": f"sms-{uuid.uuid4().hex[:8]}",
            "to": to,
            "message": message,
            "sent_at": time.time(),
        }
        self._outbox.append(record)
        logger.info(f"[mock sms] -> {to}: {message}")
        return dict(record)

    def outbox(self) -> list[dict]:
        return [dict(r) for r in self._outbox]


class MockEmailSender:
    """Records every 'sent' email instead of calling a real email provider."""

    def __init__(self) -> None:
        self._outbox: list[dict] = []

    def send(self, to: str, subject: str, message: str) -> dict:
        record = {
            "id": f"email-{uuid.uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "message": message,
            "sent_at": time.time(),
        }
        self._outbox.append(record)
        logger.info(f"[mock email] -> {to} ({subject}): {message}")
        return dict(record)

    def outbox(self) -> list[dict]:
        return [dict(r) for r in self._outbox]


sms_sender = MockSmsSender()
email_sender = MockEmailSender()

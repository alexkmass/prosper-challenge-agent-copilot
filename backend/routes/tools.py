#
# Dev/verification endpoints over the dummy tool backends (bookings, CRM,
# notification outbox, reminders). No dedicated frontend panel — these exist
# for manual verification and demoing (see specs/agent-tools.md).
#

from typing import Optional

from fastapi import APIRouter, HTTPException

from tools.booking_store import booking_store
from tools.crm_store import crm_store
from tools.notifications import email_sender, sms_sender
from tools.registry import tool_catalog
from tools.scheduler import reminder_scheduler

router = APIRouter(prefix="/api/tools", tags=["tools"])


@router.get("/catalog")
async def get_tool_catalog():
    """Edge-tool metadata for the builder UI and Copilot context."""
    return tool_catalog()


@router.get("/slots")
async def list_slots(service: Optional[str] = None, date: Optional[str] = None):
    return booking_store.list_available_slots(service=service, date=date)


@router.get("/bookings")
async def list_bookings():
    return booking_store.list_bookings()


@router.get("/crm")
async def list_crm_contacts():
    return crm_store.list_contacts()


@router.get("/outbox/sms")
async def list_sms_outbox():
    return sms_sender.outbox()


@router.get("/outbox/email")
async def list_email_outbox():
    return email_sender.outbox()


@router.get("/reminders")
async def list_reminders():
    return reminder_scheduler.list()


@router.post("/reminders/{reminder_id}/fire")
async def fire_reminder(reminder_id: str):
    """Send a scheduled reminder now instead of waiting out its real run_at (demo aid)."""
    try:
        return reminder_scheduler.fire(reminder_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

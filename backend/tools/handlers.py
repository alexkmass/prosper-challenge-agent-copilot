#
# The 6 edge-tool handlers wired into TOOL_REGISTRY (registry.py). Each has
# signature (args, state) -> dict; the dict is merged into both the LLM's
# function result and flow_manager.state (see agent_builder/builder.py) —
# unless the edge runs it with tool_async, in which case only state gets it,
# once the background task finishes. A ValueError raised here is already
# caught by Pipecat Flows itself and relayed to the LLM as a graceful error
# rather than a crash, so failure messages here are written to be spoken aloud.
#

from datetime import datetime, timedelta
from typing import Optional

from .booking_store import booking_store
from .crm_store import crm_store
from .notifications import email_sender, sms_sender
from .scheduler import reminder_scheduler


def resolve_full_name(args: dict, state: dict) -> tuple[Optional[str], Optional[str]]:
    """first_name/last_name if collected as such, else split a `full_name`
    (however it made it into args/state) on the first space.
    """
    first = args.get("first_name") or state.get("first_name")
    last = args.get("last_name") or state.get("last_name")
    if first and last:
        return first, last
    full_name = args.get("full_name") or state.get("full_name")
    if full_name:
        parts = full_name.strip().split(None, 1)
        return parts[0], (parts[1] if len(parts) > 1 else "")
    return None, None


async def appointment_lookup(args: dict, state: dict) -> dict:
    slots = booking_store.list_available_slots(service=args.get("service"), date=args.get("date"))
    return {"available_slots": slots}


async def appointment_book(args: dict, state: dict) -> dict:
    caller_name = (
        args.get("caller_name") or state.get("caller_name") or state.get("full_name") or "the caller"
    )
    phone = args.get("phone_number") or state.get("phone_number")
    email = args.get("email") or state.get("email")
    crm_contact_id = state.get("crm_contact_id")

    slot_id = args.get("slot_id")
    if slot_id:
        booking = booking_store.book_slot(
            slot_id, caller_name, phone=phone, email=email, crm_contact_id=crm_contact_id
        )
    else:
        # No live slot catalog was offered on this transition (e.g. a fixed small
        # menu) — book against whatever label the caller picked instead.
        label = args.get("slot") or args.get("time_label")
        if not label:
            raise ValueError("I need to know which time was chosen before I can book it.")
        booking = booking_store.book_label(
            label, caller_name, phone=phone, email=email, crm_contact_id=crm_contact_id
        )

    reminder = None
    try:
        remind_at = datetime.fromisoformat(booking["start"]) - timedelta(hours=1)
    except ValueError:
        remind_at = None  # a free-text label (book_label), not a real datetime
    if remind_at:
        service = booking["service"].replace("_", " ") if booking["service"] else "appointment"
        message = f"Reminder: your {service} is in 1 hour."
        if phone:
            reminder = reminder_scheduler.schedule(remind_at, "sms", phone, message)
        elif email:
            reminder = reminder_scheduler.schedule(remind_at, "email", email, message)

    return {
        "booking_id": booking["id"],
        "confirmed_slot": booking,
        "reminder_scheduled": reminder is not None,
    }


async def crm_lookup(args: dict, state: dict) -> dict:
    first_name, last_name = resolve_full_name(args, state)
    if not first_name:
        raise ValueError("I still need the caller's name before I can look them up.")
    contact = crm_store.find_by_name(first_name, last_name or "")
    return {"crm_found": contact is not None, "contact": contact}


async def crm_create(args: dict, state: dict) -> dict:
    first_name, last_name = resolve_full_name(args, state)
    if not first_name:
        raise ValueError("I still need the caller's name before I can set up their file.")
    insurance_id = (
        args.get("insurance_id")
        or args.get("member_id")
        or state.get("insurance_id")
        or state.get("member_id")
    )
    phone_number = args.get("phone_number") or state.get("phone_number")
    email = args.get("email") or state.get("email")

    existing = crm_store.find_by_name(first_name, last_name or "")
    if existing:
        return {"crm_contact_id": existing["id"], "crm_created": False}
    contact = crm_store.create_contact(
        first_name, last_name or "", insurance_id=insurance_id, phone_number=phone_number, email=email
    )
    return {"crm_contact_id": contact["id"], "crm_created": True}


async def send_sms(args: dict, state: dict) -> dict:
    to = args.get("phone_number") or state.get("phone_number")
    if not to:
        raise ValueError("There's no phone number on file to text.")
    record = sms_sender.send(to, args["message"])
    return {"sms_status": "sent", "sms_id": record["id"]}


async def send_email(args: dict, state: dict) -> dict:
    to = args.get("email") or state.get("email")
    if not to:
        raise ValueError("There's no email address on file to write to.")
    record = email_sender.send(to, args["subject"], args["message"])
    return {"email_status": "sent", "email_id": record["id"]}

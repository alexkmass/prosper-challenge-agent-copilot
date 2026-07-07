#
# TOOL_REGISTRY — the catalog of edge-level tools. AgentBuilder validates
# Edge.tool against this dict's keys and, when set, awaits the tool's handler
# before transitioning (see agent_builder/builder.py). The frontend's
# lib/toolCatalog.ts is a hand-kept UI mirror of the same 5 entries (same
# pattern as types/agent.ts mirroring schema.py).
#

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from . import handlers

ToolHandler = Callable[[dict, dict], Awaitable[dict]]


@dataclass
class ToolSpec:
    key: str
    label: str
    category: str
    default_function: str
    default_description: str
    handler: ToolHandler
    default_properties: dict = field(default_factory=dict)
    default_required: list = field(default_factory=list)


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "appointment_lookup": ToolSpec(
        key="appointment_lookup",
        label="Look up available appointment slots",
        category="Appointments",
        default_function="find_available_slots",
        default_description=(
            "Call this when the caller wants to know what appointment times are open, "
            "optionally for a specific service or date."
        ),
        default_properties={
            "service": {
                "type": "string",
                "description": "The service requested, e.g. general_checkup or dental_cleaning.",
            },
            "date": {
                "type": "string",
                "description": "Preferred date (YYYY-MM-DD), if the caller mentioned one.",
            },
        },
        handler=handlers.appointment_lookup,
    ),
    "appointment_book": ToolSpec(
        key="appointment_book",
        label="Book an appointment slot",
        category="Appointments",
        default_function="book_appointment",
        default_description="Call this once the caller has picked a specific available slot to book.",
        default_properties={
            "slot_id": {"type": "string", "description": "The id of the slot the caller chose."},
            "caller_name": {"type": "string", "description": "The caller's full name for the booking."},
            "phone_number": {
                "type": "string",
                "description": "Caller's phone number, for confirmation/reminder texts.",
            },
            "email": {
                "type": "string",
                "description": "Caller's email, for confirmation/reminder emails.",
            },
        },
        default_required=["slot_id", "caller_name"],
        handler=handlers.appointment_book,
    ),
    "crm_lookup": ToolSpec(
        key="crm_lookup",
        label="Look up caller in CRM",
        category="CRM",
        default_function="lookup_crm_contact",
        default_description=(
            "Call this as soon as you have the caller's first and last name, to check "
            "whether they're an existing contact."
        ),
        default_properties={
            "first_name": {"type": "string", "description": "Caller's first name."},
            "last_name": {"type": "string", "description": "Caller's last name."},
        },
        default_required=["first_name", "last_name"],
        handler=handlers.crm_lookup,
    ),
    "crm_create": ToolSpec(
        key="crm_create",
        label="Create caller in CRM",
        category="CRM",
        default_function="create_crm_contact",
        default_description=(
            "Call this once you have the caller's name and insurance details, to create "
            "(or reuse, if they already exist) their CRM record. Side-effect only — "
            "usually safe to run in the background."
        ),
        default_properties={
            "first_name": {"type": "string", "description": "Caller's first name."},
            "last_name": {"type": "string", "description": "Caller's last name."},
            "insurance_id": {"type": "string", "description": "Insurance member id, if given."},
            "phone_number": {"type": "string", "description": "Caller's phone number, if given."},
            "email": {"type": "string", "description": "Caller's email, if given."},
        },
        default_required=["first_name", "last_name"],
        handler=handlers.crm_create,
    ),
    "send_sms": ToolSpec(
        key="send_sms",
        label="Send confirmation text",
        category="Notifications",
        default_function="send_confirmation_sms",
        default_description="Call this to text the caller a confirmation or summary of what was just arranged.",
        default_properties={
            "phone_number": {
                "type": "string",
                "description": "Where to send the text, if not already known.",
            },
            "message": {"type": "string", "description": "The text message body."},
        },
        default_required=["message"],
        handler=handlers.send_sms,
    ),
    "send_email": ToolSpec(
        key="send_email",
        label="Send confirmation email",
        category="Notifications",
        default_function="send_confirmation_email",
        default_description="Call this to email the caller a confirmation or summary of what was just arranged.",
        default_properties={
            "email": {
                "type": "string",
                "description": "Where to send the email, if not already known.",
            },
            "subject": {"type": "string", "description": "The email subject line."},
            "message": {"type": "string", "description": "The email body."},
        },
        default_required=["subject", "message"],
        handler=handlers.send_email,
    ),
}

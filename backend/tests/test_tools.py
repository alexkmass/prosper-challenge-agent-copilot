"""
Fast, deterministic unit tests for backend/tools/ — no LLM calls. Covers the
dummy stores/senders/scheduler behind the 5 edge tools, the global
human-escalation functions AgentBuilder injects into every non-terminal node,
and the two new validation rules on Edge.tool / reserved function names. See
specs/agent-tools.md.
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from agent_builder import AgentBuilder
from tools import handlers
from tools.booking_store import InMemoryBookingStore
from tools.crm_store import InMemoryCrmStore
from tools.human_handoff import CONFIRM_HUMAN_FUNCTION, REQUEST_HUMAN_FUNCTION
from tools.notifications import MockEmailSender, MockSmsSender
from tools.scheduler import InMemoryReminderScheduler


class _FakeFlowManager:
    def __init__(self, state=None):
        self.state = state or {}


# ---- booking store ----------------------------------------------------


def test_list_available_slots_filters_by_service_and_date():
    store = InMemoryBookingStore()
    all_slots = store.list_available_slots()
    assert all_slots

    service = all_slots[0]["service"]
    assert all(s["service"] == service for s in store.list_available_slots(service=service))

    date = all_slots[0]["start"][:10]
    assert all(s["start"].startswith(date) for s in store.list_available_slots(date=date))


def test_book_slot_marks_unavailable_and_rejects_rebooking():
    store = InMemoryBookingStore()
    slot = store.list_available_slots()[0]
    booking = store.book_slot(slot["id"], "Jamie Lee", phone="+1-555-0000")
    assert booking["slot_id"] == slot["id"]
    assert slot["id"] not in {s["id"] for s in store.list_available_slots()}
    with pytest.raises(ValueError, match="isn't available anymore"):
        store.book_slot(slot["id"], "Someone Else")


def test_book_unknown_slot_rejected():
    store = InMemoryBookingStore()
    with pytest.raises(ValueError, match="no appointment slot"):
        store.book_slot("slot-does-not-exist", "Jamie Lee")


# ---- CRM store ----------------------------------------------------


def test_crm_lookup_seeded_contact_found():
    contact = InMemoryCrmStore().find_by_name("Jordan", "Reyes")
    assert contact is not None
    assert contact["insurance_id"] == "INS-4821"


def test_crm_lookup_unknown_contact_not_found():
    assert InMemoryCrmStore().find_by_name("Nobody", "Here") is None


def test_crm_create_contact_then_found():
    store = InMemoryCrmStore()
    store.create_contact("New", "Caller", phone_number="+1-555-9999")
    contact = store.find_by_name("New", "Caller")
    assert contact is not None
    assert contact["phone_number"] == "+1-555-9999"


# ---- notifications + scheduler ----------------------------------------------------


def test_mock_senders_record_outbox():
    sms, email = MockSmsSender(), MockEmailSender()
    sms.send("+1-555-1111", "hello")
    email.send("a@example.com", "subject", "body")
    assert len(sms.outbox()) == 1
    assert len(email.outbox()) == 1


def test_reminder_schedule_list_and_fire():
    sms, email = MockSmsSender(), MockEmailSender()
    scheduler = InMemoryReminderScheduler(sms, email)
    reminder = scheduler.schedule(
        datetime.now() + timedelta(hours=1), "sms", "+1-555-2222", "reminder text"
    )
    assert reminder["status"] == "pending"
    assert scheduler.list() == [reminder]

    fired = scheduler.fire(reminder["id"])
    assert fired["status"] == "sent"
    assert len(sms.outbox()) == 1


def test_fire_unknown_reminder_rejected():
    scheduler = InMemoryReminderScheduler(MockSmsSender(), MockEmailSender())
    with pytest.raises(ValueError, match="No reminder"):
        scheduler.fire("nope")


# ---- handlers (fresh stores per test, via monkeypatched singletons) ---------------


@pytest.fixture
async def isolated_handlers(monkeypatch):
    stores = {
        "booking": InMemoryBookingStore(),
        "crm": InMemoryCrmStore(),
        "sms": MockSmsSender(),
        "email": MockEmailSender(),
    }
    stores["scheduler"] = InMemoryReminderScheduler(stores["sms"], stores["email"])
    monkeypatch.setattr(handlers, "booking_store", stores["booking"])
    monkeypatch.setattr(handlers, "crm_store", stores["crm"])
    monkeypatch.setattr(handlers, "sms_sender", stores["sms"])
    monkeypatch.setattr(handlers, "email_sender", stores["email"])
    monkeypatch.setattr(handlers, "reminder_scheduler", stores["scheduler"])
    yield stores
    # appointment_book may have started the scheduler's background poll loop —
    # cancel it so it doesn't outlive this test's event loop.
    loop_task = stores["scheduler"]._loop_task
    if loop_task is not None:
        loop_task.cancel()


async def test_appointment_lookup_handler_returns_available_slots(isolated_handlers):
    result = await handlers.appointment_lookup({}, {})
    assert result["available_slots"]


async def test_appointment_book_handler_books_and_schedules_reminder(isolated_handlers):
    slot = isolated_handlers["booking"].list_available_slots()[0]
    result = await handlers.appointment_book(
        {"slot_id": slot["id"], "caller_name": "Jamie Lee", "phone_number": "+1-555-3333"}, {}
    )
    assert result["booking_id"]
    assert result["reminder_scheduled"] is True
    assert isolated_handlers["scheduler"].list()


async def test_appointment_book_without_contact_skips_reminder(isolated_handlers):
    slot = isolated_handlers["booking"].list_available_slots()[0]
    result = await handlers.appointment_book({"slot_id": slot["id"], "caller_name": "No Contact"}, {})
    assert result["reminder_scheduled"] is False
    assert isolated_handlers["scheduler"].list() == []


async def test_crm_lookup_handler_found_and_not_found(isolated_handlers):
    isolated_handlers["crm"].create_contact("Sam", "Rivera")
    found = await handlers.crm_lookup({"first_name": "Sam", "last_name": "Rivera"}, {})
    assert found["crm_found"] is True

    missing = await handlers.crm_lookup({"first_name": "No", "last_name": "One"}, {})
    assert missing["crm_found"] is False


async def test_crm_lookup_handler_splits_full_name_fallback(isolated_handlers):
    isolated_handlers["crm"].create_contact("Sam", "Rivera")
    found = await handlers.crm_lookup({}, {"full_name": "Sam Rivera"})
    assert found["crm_found"] is True


async def test_crm_create_handler_creates_then_reuses(isolated_handlers):
    created = await handlers.crm_create(
        {"first_name": "New", "last_name": "Caller", "member_id": "M1"}, {}
    )
    assert created["crm_created"] is True
    contact_id = created["crm_contact_id"]

    reused = await handlers.crm_create({"first_name": "New", "last_name": "Caller"}, {})
    assert reused["crm_created"] is False
    assert reused["crm_contact_id"] == contact_id


async def test_crm_create_handler_requires_a_name(isolated_handlers):
    with pytest.raises(ValueError, match="caller's name"):
        await handlers.crm_create({}, {})


async def test_appointment_book_handler_falls_back_to_label_and_links_crm_contact(isolated_handlers):
    result = await handlers.appointment_book(
        {"slot": "Thursday 2 PM", "caller_name": "Nora Fields"},
        {"crm_contact_id": "contact-123"},
    )
    assert result["reminder_scheduled"] is False  # a label isn't a real datetime
    booking = isolated_handlers["booking"].list_bookings()[0]
    assert booking["start"] == "Thursday 2 PM"
    assert booking["crm_contact_id"] == "contact-123"


async def test_appointment_book_handler_requires_a_slot_or_label(isolated_handlers):
    with pytest.raises(ValueError, match="which time was chosen"):
        await handlers.appointment_book({"caller_name": "Nora Fields"}, {})


async def test_send_sms_handler_falls_back_to_state_for_recipient(isolated_handlers):
    result = await handlers.send_sms({"message": "hi"}, {"phone_number": "+1-555-4444"})
    assert result["sms_status"] == "sent"
    assert isolated_handlers["sms"].outbox()[0]["to"] == "+1-555-4444"


async def test_send_sms_handler_requires_a_recipient(isolated_handlers):
    with pytest.raises(ValueError, match="no phone number"):
        await handlers.send_sms({"message": "hi"}, {})


async def test_send_email_handler_requires_a_recipient(isolated_handlers):
    with pytest.raises(ValueError, match="no email address"):
        await handlers.send_email({"subject": "s", "message": "m"}, {})


# ---- AgentBuilder integration ----------------------------------------------------


def _agent_with_edge(edge: dict) -> dict:
    return {
        "name": "tool-test",
        "initial_node": "start",
        "nodes": [
            {"name": "start", "task_messages": [], "edges": [edge]},
            {"name": "end", "task_messages": [], "edges": [], "end": True},
        ],
    }


def test_unknown_tool_key_rejected():
    edge = {"function": "f", "description": "d", "target": "end", "tool": "not_a_real_tool"}
    with pytest.raises(ValueError, match="unknown tool"):
        AgentBuilder.from_dict(_agent_with_edge(edge))


@pytest.mark.parametrize("name", [REQUEST_HUMAN_FUNCTION, CONFIRM_HUMAN_FUNCTION])
def test_reserved_function_name_rejected(name):
    edge = {"function": name, "description": "d", "target": "end"}
    with pytest.raises(ValueError, match="reserved function name"):
        AgentBuilder.from_dict(_agent_with_edge(edge))


def test_non_terminal_node_gets_global_functions(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    names = {f.name for f in builder.build_initial_node()["functions"]}
    assert REQUEST_HUMAN_FUNCTION in names
    assert CONFIRM_HUMAN_FUNCTION in names


def test_terminal_node_has_no_global_functions(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    node_config = builder._make_node(builder._nodes_by_name["confirm"])
    assert node_config["functions"] == []


async def test_confirm_human_transfer_produces_valid_terminal_node(scheduler_config):
    builder = AgentBuilder.from_dict(scheduler_config)
    node_config = builder.build_initial_node()
    confirm_fn = next(f for f in node_config["functions"] if f.name == CONFIRM_HUMAN_FUNCTION)

    result, next_node = await confirm_fn.handler({}, _FakeFlowManager())
    assert result["status"] == "connected"
    assert next_node["post_actions"] == [{"type": "end_conversation"}]
    assert next_node["functions"] == []


async def test_tool_edge_merges_handler_result_into_llm_response_and_state(monkeypatch):
    monkeypatch.setattr(handlers, "crm_store", InMemoryCrmStore())
    config = _agent_with_edge(
        {
            "function": "lookup",
            "description": "d",
            "target": "end",
            "tool": "crm_lookup",
            "properties": {"first_name": {"type": "string"}, "last_name": {"type": "string"}},
            "required": ["first_name", "last_name"],
        }
    )
    builder = AgentBuilder.from_dict(config)
    fn = next(f for f in builder.build_initial_node()["functions"] if f.name == "lookup")

    flow_manager = _FakeFlowManager()
    result, _ = await fn.handler({"first_name": "Jordan", "last_name": "Reyes"}, flow_manager)
    assert result["crm_found"] is True
    assert flow_manager.state["crm_found"] is True


def test_tool_async_without_tool_rejected():
    edge = {"function": "f", "description": "d", "target": "end", "tool_async": True}
    with pytest.raises(ValueError, match="tool_async but has no tool"):
        AgentBuilder.from_dict(_agent_with_edge(edge))


async def test_tool_async_edge_does_not_block_and_updates_state_later(monkeypatch):
    monkeypatch.setattr(handlers, "crm_store", InMemoryCrmStore())
    config = _agent_with_edge(
        {
            "function": "create_user",
            "description": "d",
            "target": "end",
            "tool": "crm_create",
            "tool_async": True,
            "properties": {"first_name": {"type": "string"}, "last_name": {"type": "string"}},
            "required": ["first_name", "last_name"],
        }
    )
    builder = AgentBuilder.from_dict(config)
    fn = next(f for f in builder.build_initial_node()["functions"] if f.name == "create_user")

    flow_manager = _FakeFlowManager()
    result, _ = await fn.handler({"first_name": "New", "last_name": "Caller"}, flow_manager)
    # This turn's response never waits for the tool — no crm_contact_id yet.
    assert "crm_contact_id" not in result
    assert "crm_contact_id" not in flow_manager.state

    for _ in range(10):
        if "crm_contact_id" in flow_manager.state:
            break
        await asyncio.sleep(0)
    assert flow_manager.state["crm_contact_id"]


# ---- Prosper Scheduler (Branched) example wiring ----------------------------------


def test_scheduler_example_wires_crm_and_booking_tools(scheduler_config):
    by_name = {n["name"]: n for n in scheduler_config["nodes"]}

    record_details = next(e for e in by_name["collect_details"]["edges"] if e["function"] == "record_details")
    assert record_details["tool"] == "crm_lookup"
    assert not record_details.get("tool_async")

    record_insurance = next(
        e for e in by_name["verify_insurance"]["edges"] if e["function"] == "record_insurance"
    )
    assert record_insurance["tool"] == "crm_create"
    assert record_insurance["tool_async"] is True

    select_time = next(e for e in by_name["offer_times"]["edges"] if e["function"] == "select_time")
    assert select_time["tool"] == "appointment_book"
    assert not select_time.get("tool_async")


async def test_scheduler_example_end_to_end_links_async_crm_contact_to_booking(monkeypatch, scheduler_config):
    monkeypatch.setattr(handlers, "crm_store", InMemoryCrmStore())
    monkeypatch.setattr(handlers, "booking_store", InMemoryBookingStore())

    builder = AgentBuilder.from_dict(scheduler_config)
    flow_manager = _FakeFlowManager()

    collect_details_node = builder._make_node(builder._nodes_by_name["collect_details"])
    record_details = next(f for f in collect_details_node["functions"] if f.name == "record_details")
    _, verify_insurance_node = await record_details.handler(
        {"full_name": "Nora Fields", "reason": "annual checkup"}, flow_manager
    )

    record_insurance = next(f for f in verify_insurance_node["functions"] if f.name == "record_insurance")
    result, offer_times_node = await record_insurance.handler(
        {"has_insurance": True, "member_id": "MID-777"}, flow_manager
    )
    assert "crm_contact_id" not in result  # fire-and-forget: not back yet

    for _ in range(10):
        if "crm_contact_id" in flow_manager.state:
            break
        await asyncio.sleep(0)
    assert flow_manager.state["crm_contact_id"]

    select_time = next(f for f in offer_times_node["functions"] if f.name == "select_time")
    booking_result, _ = await select_time.handler({"slot": "Thursday 2 PM"}, flow_manager)
    assert booking_result["confirmed_slot"]["crm_contact_id"] == flow_manager.state["crm_contact_id"]

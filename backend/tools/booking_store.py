#
# In-memory appointment slots + bookings DB — the backing store for the
# `appointment_lookup` / `appointment_book` tools (see registry.py).
#
# Kept behind a small interface (BookingStore), same shape as backend/store.py,
# so a real scheduling system can replace InMemoryBookingStore later without
# touching handlers.py.
#

import uuid
from datetime import datetime, timedelta
from typing import Optional, Protocol

SERVICES = ["general_checkup", "dental_cleaning"]


class BookingStore(Protocol):
    """Everything the appointment tools need from a store — swap the impl freely."""

    def list_available_slots(
        self, service: Optional[str] = None, date: Optional[str] = None
    ) -> list[dict]: ...
    def get_slot(self, slot_id: str) -> Optional[dict]: ...
    def book_slot(
        self,
        slot_id: str,
        caller_name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        crm_contact_id: Optional[str] = None,
    ) -> dict: ...
    def book_label(
        self,
        label: str,
        caller_name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        crm_contact_id: Optional[str] = None,
    ) -> dict: ...
    def list_bookings(self) -> list[dict]: ...


class InMemoryBookingStore:
    """Dict-backed BookingStore, seeded with a few days of slots. Not persisted."""

    def __init__(self) -> None:
        self._slots: dict[str, dict] = {}
        self._bookings: dict[str, dict] = {}
        self._seed()

    def _seed(self) -> None:
        anchor = datetime.now().replace(minute=0, second=0, microsecond=0)
        slot_num = 1
        for day_offset in range(1, 6):  # the next 5 days
            day = anchor + timedelta(days=day_offset)
            for hour in (9, 11, 14, 16):
                for service in SERVICES:
                    slot_id = f"slot-{slot_num}"
                    slot_num += 1
                    self._slots[slot_id] = {
                        "id": slot_id,
                        "service": service,
                        "start": day.replace(hour=hour).isoformat(),
                        "duration_minutes": 30,
                        "available": True,
                    }

    def list_available_slots(
        self, service: Optional[str] = None, date: Optional[str] = None
    ) -> list[dict]:
        results = [
            dict(slot)
            for slot in self._slots.values()
            if slot["available"]
            and (service is None or slot["service"] == service)
            and (date is None or slot["start"].startswith(date))
        ]
        results.sort(key=lambda s: s["start"])
        return results

    def get_slot(self, slot_id: str) -> Optional[dict]:
        slot = self._slots.get(slot_id)
        return dict(slot) if slot else None

    def book_slot(
        self,
        slot_id: str,
        caller_name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        crm_contact_id: Optional[str] = None,
    ) -> dict:
        slot = self._slots.get(slot_id)
        if slot is None:
            raise ValueError(f"There's no appointment slot called '{slot_id}'.")
        if not slot["available"]:
            raise ValueError("That slot isn't available anymore — please choose another time.")
        slot["available"] = False
        booking = {
            "id": f"booking-{uuid.uuid4().hex[:8]}",
            "slot_id": slot_id,
            "caller_name": caller_name,
            "phone": phone,
            "email": email,
            "service": slot["service"],
            "start": slot["start"],
            "duration_minutes": slot["duration_minutes"],
            "crm_contact_id": crm_contact_id,
        }
        self._bookings[booking["id"]] = booking
        return dict(booking)

    def book_label(
        self,
        label: str,
        caller_name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        crm_contact_id: Optional[str] = None,
    ) -> dict:
        """Record a booking against a free-text time label instead of a catalog slot id —
        for flows (like a fixed small menu) that never called appointment_lookup. `start`
        isn't a real datetime here, so no reminder can be scheduled off it.
        """
        booking = {
            "id": f"booking-{uuid.uuid4().hex[:8]}",
            "slot_id": None,
            "caller_name": caller_name,
            "phone": phone,
            "email": email,
            "service": None,
            "start": label,
            "duration_minutes": None,
            "crm_contact_id": crm_contact_id,
        }
        self._bookings[booking["id"]] = booking
        return dict(booking)

    def list_bookings(self) -> list[dict]:
        return [dict(b) for b in self._bookings.values()]


booking_store = InMemoryBookingStore()

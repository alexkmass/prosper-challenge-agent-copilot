#
# In-memory CRM contacts DB — the backing store for the `crm_lookup` tool and
# the post-call "create if missing" step (see bot.py's on_client_disconnected).
#
# Same swappable shape as backend/store.py — a real CRM integration means
# writing one class, not touching handlers.py or bot.py.
#

import uuid
from typing import Optional, Protocol


class CrmStore(Protocol):
    """Everything the CRM tool + post-call hook need from a store."""

    def find_by_name(self, first_name: str, last_name: str) -> Optional[dict]: ...
    def create_contact(
        self,
        first_name: str,
        last_name: str,
        insurance_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict: ...
    def list_contacts(self) -> list[dict]: ...


def _key(first_name: str, last_name: str) -> str:
    return f"{first_name.strip().lower()}|{last_name.strip().lower()}"


class InMemoryCrmStore:
    """Dict-backed CrmStore, seeded with a couple of example contacts. Not persisted."""

    def __init__(self) -> None:
        self._contacts: dict[str, dict] = {}
        self._seed()

    def _seed(self) -> None:
        for contact in (
            {
                "first_name": "Jordan",
                "last_name": "Reyes",
                "insurance_id": "INS-4821",
                "phone_number": "+1-555-0142",
                "email": "jordan.reyes@example.com",
            },
            {
                "first_name": "Amara",
                "last_name": "Okafor",
                "insurance_id": "INS-1190",
                "phone_number": "+1-555-0198",
                "email": "amara.okafor@example.com",
            },
        ):
            self._contacts[_key(contact["first_name"], contact["last_name"])] = {
                "id": f"contact-{uuid.uuid4().hex[:8]}",
                **contact,
            }

    def find_by_name(self, first_name: str, last_name: str) -> Optional[dict]:
        contact = self._contacts.get(_key(first_name, last_name))
        return dict(contact) if contact else None

    def create_contact(
        self,
        first_name: str,
        last_name: str,
        insurance_id: Optional[str] = None,
        phone_number: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict:
        contact = {
            "id": f"contact-{uuid.uuid4().hex[:8]}",
            "first_name": first_name,
            "last_name": last_name,
            "insurance_id": insurance_id,
            "phone_number": phone_number,
            "email": email,
        }
        self._contacts[_key(first_name, last_name)] = contact
        return dict(contact)

    def list_contacts(self) -> list[dict]:
        return [dict(c) for c in self._contacts.values()]


crm_store = InMemoryCrmStore()

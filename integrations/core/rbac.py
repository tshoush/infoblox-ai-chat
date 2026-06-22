"""Platform-agnostic role-based access control for the chat adapters.

Fail-closed: with no writers configured, the bot answers questions for everyone
but refuses every change. Each platform builds an Rbac from its own env vars
(user-id namespaces differ: Slack ``U…``, Teams AAD ids, WhatsApp phone numbers):

    Rbac.from_env("SLACK")     # SLACK_WRITER_USERS / SLACK_ADMIN_USERS
    Rbac.from_env("TEAMS")     # TEAMS_WRITER_USERS / TEAMS_ADMIN_USERS
    Rbac.from_env("WHATSAPP")  # WHATSAPP_WRITER_USERS / WHATSAPP_ADMIN_USERS
"""
import os
from typing import Iterable, List, Tuple


def parse_ids(value: str) -> List[str]:
    return [u.strip() for u in (value or "").split(",") if u.strip()]


class Rbac:
    def __init__(self, writers: Iterable[str] = (), admins: Iterable[str] = ()):
        self.writers = set(writers or [])
        self.admins = set(admins or [])
        self.writers |= self.admins  # admins are implicitly writers

    @classmethod
    def from_env(cls, prefix: str) -> "Rbac":
        return cls(parse_ids(os.getenv(f"{prefix}_WRITER_USERS", "")),
                   parse_ids(os.getenv(f"{prefix}_ADMIN_USERS", "")))

    def can_write(self, user_id: str) -> bool:
        return user_id in self.writers

    def can_delete(self, user_id: str) -> bool:
        return user_id in self.admins

    def authorize(self, user_id: str, operations: list) -> Tuple[bool, str]:
        """Returns (allowed, reason) for a plan of operations."""
        methods = {(op.get("method") or "GET").upper() for op in operations if isinstance(op, dict)}
        if not (methods - {"GET"}):
            return True, ""  # read-only
        if not self.can_write(user_id):
            return False, "You don't have permission to make changes. Ask a NetOps operator to approve."
        if "DELETE" in methods and not self.can_delete(user_id):
            return False, "Deletes are destructive and require an admin to approve."
        return True, ""

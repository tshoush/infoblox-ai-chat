"""Shared conversation/approval logic for all chat adapters.

Each adapter calls :func:`plan_for_message` to decide what to say, and (on an
Approve action) :func:`run_approval`. Platform-specific code only renders the
result and wires events — keeping Slack/Teams/WhatsApp thin and consistent.
"""
import os
import threading
import time
import uuid
from typing import Any, Dict


class PendingStore:
    """Single-use, time-bounded store of approved-pending plans.

    ``take`` is atomic and single-use → idempotency against duplicate button
    clicks / platform retries. Entries expire after ``ttl`` seconds (a stale
    approval must not run), and the store is capped so abandoned proposals can't
    grow memory without bound. Thread-safe (Slack Bolt / aiohttp dispatch on
    worker threads)."""

    def __init__(self, ttl: int = 900, max_items: int = 1000):
        self._items: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max = max_items

    def _purge(self, now: float) -> None:
        for k in [k for k, v in self._items.items() if now - v["ts"] > self._ttl]:
            self._items.pop(k, None)
        if len(self._items) > self._max:
            oldest = sorted(self._items, key=lambda k: self._items[k]["ts"])
            for k in oldest[: len(self._items) - self._max]:
                self._items.pop(k, None)

    def put(self, operations, session_id, requester, ticket=None) -> str:
        token = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._purge(now)
            self._items[token] = {"operations": operations, "session_id": session_id,
                                  "requester": requester, "ticket": ticket, "ts": now}
        return token

    def take(self, token: str):
        now = time.time()
        with self._lock:
            item = self._items.pop(token, None)
        if item and now - item["ts"] > self._ttl:
            return None  # expired
        return item


def plan_for_message(iaci, rbac, text: str, user_id: str, session_id: str = None,
                     ticket_policy=None) -> Dict[str, Any]:
    """Returns one of:
      {"kind": "help"}
      {"kind": "answer",      "text": str}
      {"kind": "approval",    "operations": [...], "warnings": [...], "ticket": str|None}
      {"kind": "needs_ticket","reason": str}
      {"kind": "denied",      "reason": str}
      {"kind": "error",       "text": str}
    """
    if not text or not text.strip():
        return {"kind": "help"}
    try:
        result = iaci.agent(text, session_id=session_id)
    except Exception as e:  # noqa: BLE001
        # Generic user-facing text; the detail is for server logs only (don't
        # leak backend host/exception internals to the chat).
        return {"kind": "error",
                "text": "Sorry — I couldn't reach the backend just now. Please try again.",
                "detail": str(e)}

    if not result.get("requires_approval"):
        return {"kind": "answer", "text": result.get("answer") or "(no answer)"}

    operations = result.get("plan", [])
    allowed, reason = rbac.authorize(user_id, operations)
    if not allowed:
        return {"kind": "denied", "reason": reason}

    # Change-management gate: a write may require a Jira/ServiceNow reference.
    ticket = None
    if ticket_policy is not None:
        ok, ticket, why = ticket_policy.check(text)
        if not ok:
            return {"kind": "needs_ticket", "reason": why}

    return {"kind": "approval", "operations": operations,
            "warnings": result.get("warnings", []), "ticket": ticket}


def run_approval(iaci, rbac, pending: Dict[str, Any], approver: str,
                 require_second_approver: bool = None) -> Dict[str, Any]:
    """Re-authorizes the approver, executes, and returns a result summary."""
    operations = pending["operations"]

    # Optional four-eyes: the approver must be a different person than the requester.
    if require_second_approver is None:
        require_second_approver = os.getenv("IACI_REQUIRE_SECOND_APPROVER", "").lower() in ("1", "true", "yes")
    if require_second_approver and approver == pending.get("requester"):
        return {"ok": False, "reason": "A second person must approve this change (four-eyes)."}

    allowed, reason = rbac.authorize(approver, operations)
    if not allowed:
        return {"ok": False, "reason": reason}
    try:
        res = iaci.execute(operations, session_id=pending.get("session_id"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"Execution failed: {e}"}
    return {"ok": True, "operations": operations,
            "results": res.get("results", []), "summary": res.get("summary"),
            "ticket": pending.get("ticket")}

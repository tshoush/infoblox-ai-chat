"""Tests for the shared adapter core (RBAC env loading, conversation flow,
pending-approval idempotency). Platform-agnostic — no SDK needed."""
from integrations.core.rbac import Rbac
from integrations.core.conversation import PendingStore, plan_for_message, run_approval
from integrations.core.change_ticket import TicketPolicy

READ = [{"operation": "network", "method": "GET", "parameters": {}}]
WRITE = [{"operation": "network", "method": "POST", "parameters": {"network": "10.9.0.0/24"}}]


class FakeIaci:
    def __init__(self, agent_result=None, execute_result=None, fail=False):
        self._agent = agent_result or {}
        self._execute = execute_result or {"results": [{"success": True}], "summary": {"succeeded": 1, "total": 1}}
        self._fail = fail
        self.executed = []

    def agent(self, message, session_id=None):
        if self._fail:
            raise RuntimeError("boom")
        return self._agent

    def execute(self, operations, session_id=None):
        self.executed.append(operations)
        return self._execute


# --- RBAC from env ----------------------------------------------------------

def test_rbac_from_env_reads_prefixed_vars(monkeypatch):
    monkeypatch.setenv("TEAMS_WRITER_USERS", "a, b ,c")
    monkeypatch.setenv("TEAMS_ADMIN_USERS", "a")
    rbac = Rbac.from_env("TEAMS")
    assert rbac.writers == {"a", "b", "c"}
    assert rbac.can_delete("a") and not rbac.can_delete("b")


# --- conversation flow ------------------------------------------------------

def test_plan_for_message_answer():
    iaci = FakeIaci(agent_result={"requires_approval": False, "answer": "5 networks"})
    out = plan_for_message(iaci, Rbac(), "how many networks", "u1")
    assert out["kind"] == "answer" and out["text"] == "5 networks"


def test_plan_for_message_help_on_empty():
    assert plan_for_message(FakeIaci(), Rbac(), "  ", "u1")["kind"] == "help"


def test_plan_for_message_error_on_backend_failure():
    out = plan_for_message(FakeIaci(fail=True), Rbac(), "hi", "u1")
    assert out["kind"] == "error"


def test_plan_for_message_approval_for_authorized_writer():
    iaci = FakeIaci(agent_result={"requires_approval": True, "plan": WRITE,
                                  "warnings": [{"index": 0, "message": "dup"}]})
    out = plan_for_message(iaci, Rbac(writers=["u1"]), "create net", "u1")
    assert out["kind"] == "approval" and out["operations"] == WRITE


def test_plan_for_message_denied_for_unauthorized():
    iaci = FakeIaci(agent_result={"requires_approval": True, "plan": WRITE, "warnings": []})
    out = plan_for_message(iaci, Rbac(writers=["someone_else"]), "create net", "u1")
    assert out["kind"] == "denied"


# --- approval execution + idempotency --------------------------------------

def test_run_approval_executes_for_authorized_approver():
    iaci = FakeIaci()
    item = {"operations": WRITE, "session_id": "s", "requester": "u1"}
    out = run_approval(iaci, Rbac(writers=["approver"]), item, "approver")
    assert out["ok"] and iaci.executed == [WRITE]


def test_run_approval_rejects_unauthorized_approver():
    iaci = FakeIaci()
    item = {"operations": WRITE, "session_id": "s", "requester": "u1"}
    out = run_approval(iaci, Rbac(writers=["someone"]), item, "intruder")
    assert not out["ok"] and iaci.executed == []  # never executed


def test_pending_store_is_single_use():
    store = PendingStore()
    token = store.put(WRITE, "s", "u1")
    assert store.take(token)["operations"] == WRITE
    assert store.take(token) is None  # second take -> idempotent no-op


# --- change-ticket policy ---------------------------------------------------

def test_ticket_policy_extracts_jira_and_servicenow():
    p = TicketPolicy(required=True)
    assert p.extract("create network for INFRA-1234 please") == "INFRA-1234"
    assert p.extract("per CHG0012345 add a scope") == "CHG0012345"
    assert p.extract("no ticket here") is None


def test_ticket_not_required_passes_through():
    p = TicketPolicy(required=False)
    ok, ticket, reason = p.check("create network 10.0.0.0/24")
    assert ok and ticket is None


def test_ticket_required_blocks_without_reference():
    p = TicketPolicy(required=True)
    ok, ticket, reason = p.check("create network 10.0.0.0/24")
    assert not ok and ticket is None and "change-ticket" in reason.lower()


def test_ticket_required_passes_with_reference():
    p = TicketPolicy(required=True)
    ok, ticket, reason = p.check("create network 10.0.0.0/24 ref CHG0009999")
    assert ok and ticket == "CHG0009999"


def test_plan_for_message_needs_ticket_when_required():
    iaci = FakeIaci(agent_result={"requires_approval": True, "plan": WRITE, "warnings": []})
    rbac = Rbac(writers=["u1"])
    policy = TicketPolicy(required=True)
    out = plan_for_message(iaci, rbac, "create net 10.9.0.0/24", "u1", ticket_policy=policy)
    assert out["kind"] == "needs_ticket"
    # With a ticket in the message it proceeds to approval and carries the ref.
    out2 = plan_for_message(iaci, rbac, "create net 10.9.0.0/24 for INFRA-7", "u1", ticket_policy=policy)
    assert out2["kind"] == "approval" and out2["ticket"] == "INFRA-7"


def test_run_approval_carries_ticket_for_audit():
    iaci = FakeIaci()
    store = PendingStore()
    token = store.put(WRITE, "s", "u1", ticket="CHG0001")
    out = run_approval(iaci, Rbac(writers=["approver"]), store.take(token), "approver")
    assert out["ok"] and out["ticket"] == "CHG0001"


def test_ticket_blocklist_rejects_network_terms():
    p = TicketPolicy(required=True)
    assert p.extract("change VLAN-100 settings") is None   # not a ticket
    assert p.extract("AS-65000 peering") is None
    assert p.extract("ticket INFRA-1234 for this") == "INFRA-1234"
    assert p.extract("per CHG0012345") == "CHG0012345"


def test_run_approval_four_eyes_blocks_self_approval():
    iaci = FakeIaci()
    store = PendingStore()
    item = store.take(store.put(WRITE, "s", "u1"))
    out = run_approval(iaci, Rbac(writers=["u1"]), item, "u1", require_second_approver=True)
    assert not out["ok"] and "second person" in out["reason"].lower()
    assert iaci.executed == []  # never ran


def test_pending_store_expires_after_ttl():
    import time as _t
    store = PendingStore(ttl=0)
    token = store.put(WRITE, "s", "u1")
    _t.sleep(0.01)
    assert store.take(token) is None  # expired -> not actionable

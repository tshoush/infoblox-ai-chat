"""Tests for the Slack adapter's pure logic (RBAC + Block Kit rendering).

These import only the slack_bolt-free modules, so they run without the SDK.
"""
from integrations.core.rbac import Rbac
from integrations.slack import blocks

READ = [{"operation": "network", "method": "GET", "parameters": {}}]
WRITE = [{"operation": "network", "method": "POST", "parameters": {"network": "10.9.0.0/24"}}]
DELETE = [{"operation": "network", "method": "DELETE", "ref": "network/x"}]


# --- RBAC -------------------------------------------------------------------

def test_reads_allowed_for_everyone():
    rbac = Rbac(writers=[], admins=[])
    ok, _ = rbac.authorize("U_anon", READ)
    assert ok


def test_writes_denied_without_permission():
    rbac = Rbac(writers=["U_ops"], admins=[])
    ok, reason = rbac.authorize("U_random", WRITE)
    assert not ok and "permission" in reason.lower()


def test_writer_can_write_but_not_delete():
    rbac = Rbac(writers=["U_ops"], admins=["U_admin"])
    assert rbac.authorize("U_ops", WRITE)[0] is True
    ok, reason = rbac.authorize("U_ops", DELETE)
    assert not ok and "admin" in reason.lower()


def test_admin_can_delete_and_is_implicitly_writer():
    rbac = Rbac(writers=[], admins=["U_admin"])
    assert rbac.authorize("U_admin", DELETE)[0] is True
    assert rbac.authorize("U_admin", WRITE)[0] is True


def test_fail_closed_when_no_writers_configured():
    rbac = Rbac(writers=[], admins=[])
    assert rbac.authorize("U_anyone", WRITE)[0] is False


# --- Block Kit --------------------------------------------------------------

def test_proposal_blocks_have_approve_and_cancel_buttons():
    warns = [{"index": 0, "level": "warn", "message": "already exists"}]
    bl = blocks.proposal_blocks(WRITE, warns, token="tok123")
    actions = [b for b in bl if b.get("type") == "actions"][0]
    action_ids = {e["action_id"] for e in actions["elements"]}
    assert action_ids == {"iaci_run", "iaci_cancel"}
    assert all(e["value"] == "tok123" for e in actions["elements"])
    # The warning text is surfaced.
    assert any("already exists" in str(b) for b in bl)


def test_results_blocks_summarize_outcome_and_approver():
    results = [{"success": True, "data": "network/new"}]
    bl = blocks.results_blocks(WRITE, results, approver="U_admin")
    text = bl[0]["text"]["text"]
    assert "Executed 1/1" in text
    assert "U_admin" in text


def test_answer_blocks_truncate_long_text():
    bl = blocks.answer_blocks("x" * 5000)
    assert len(bl[0]["text"]["text"]) <= 2920

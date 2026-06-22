"""Pure-logic tests for the Teams (Adaptive Card) and WhatsApp (Cloud API)
message builders. No botbuilder / Flask / network needed."""
from integrations.teams import cards
from integrations.whatsapp import messages

WRITE = [{"operation": "network", "method": "POST", "parameters": {"network": "10.9.0.0/24"}}]
WARN = [{"index": 0, "level": "warn", "message": "already exists"}]


# --- Teams Adaptive Cards ---------------------------------------------------

def test_teams_proposal_card_has_submit_actions_with_token():
    card = cards.proposal_card(WRITE, WARN, token="tk1")
    assert card["type"] == "AdaptiveCard"
    actions = card["actions"]
    assert {a["data"]["iaci_action"] for a in actions} == {"run", "cancel"}
    assert all(a["data"]["token"] == "tk1" for a in actions)
    assert any("already exists" in str(b) for b in card["body"])


def test_teams_results_card_summarizes():
    card = cards.results_card(WRITE, [{"success": True, "data": "network/x"}], approver="29:abc")
    assert "Executed 1/1" in card["body"][0]["text"]
    assert "29:abc" in card["body"][0]["text"]


# --- WhatsApp Cloud API -----------------------------------------------------

def test_whatsapp_approval_message_has_reply_buttons():
    msg = messages.approval_message("15551234567", WRITE, WARN, token="tk2")
    buttons = msg["interactive"]["action"]["buttons"]
    ids = {b["reply"]["id"] for b in buttons}
    assert ids == {"run:tk2", "cancel:tk2"}
    assert "already exists" in msg["interactive"]["body"]["text"]


def test_whatsapp_body_truncated_to_limit():
    big = [{"operation": "network", "method": "POST", "parameters": {}} for _ in range(500)]
    msg = messages.approval_message("1555", big, [], token="t")
    assert len(msg["interactive"]["body"]["text"]) <= messages.BODY_MAX


def test_whatsapp_parse_inbound_text_and_button():
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "1555", "type": "text", "text": {"body": "list networks"}},
        {"from": "1555", "type": "interactive",
         "interactive": {"type": "button_reply", "button_reply": {"id": "run:tok", "title": "Approve"}}},
    ]}}]}]}
    parsed = messages.parse_inbound(payload)
    assert parsed[0] == {"from": "1555", "kind": "text", "value": "list networks"}
    assert parsed[1] == {"from": "1555", "kind": "button", "value": "run:tok"}


def test_whatsapp_parse_inbound_ignores_status_events():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"status": "delivered"}]}}]}]}
    assert messages.parse_inbound(payload) == []

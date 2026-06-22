"""WhatsApp Cloud API message builders + inbound parser (pure, testable).

WhatsApp interactive messages allow up to 3 reply buttons (title <=20 chars) and
a body <=1024 chars, so the approval card is compact: the plan/warnings go in the
body text and Approve/Cancel are reply buttons whose ids carry the token.
"""
from typing import Any, Dict, List

BODY_MAX = 1024


def _truncate(text: str, limit: int = BODY_MAX) -> str:
    return text if len(text) <= limit else text[: limit - 12] + "\n…(more)"


def text_message(to: str, text: str) -> Dict[str, Any]:
    return {"messaging_product": "whatsapp", "to": to, "type": "text",
            "text": {"body": _truncate(text, 4096)}}


def approval_message(to: str, operations: List[Dict[str, Any]],
                     warnings: List[Dict[str, Any]], token: str, ticket: str = None) -> Dict[str, Any]:
    n = len(operations)
    lines = [f"*Proposed change — {n} WAPI call{'s' if n != 1 else ''}*"]
    if ticket:
        lines.append(f"🎫 {ticket}")
    lines += [f"{i+1}. {op.get('method')} {op.get('operation')}" for i, op in enumerate(operations)]
    if warnings:
        lines.append("")
        lines += [("🛑 " if w.get("level") == "danger" else "⚠️ ")
                  + f"Step {w.get('index', 0) + 1}: {w.get('message', '')}" for w in warnings]
    body = _truncate("\n".join(lines))
    return {
        "messaging_product": "whatsapp", "to": to, "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": f"run:{token}", "title": "✅ Approve & Run"}},
                {"type": "reply", "reply": {"id": f"cancel:{token}", "title": "Cancel"}},
            ]},
        },
    }


def parse_inbound(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extracts user messages from a Cloud API webhook payload.

    Returns a list of {"from": wa_id, "kind": "text"|"button", "value": ...}.
    Ignores delivery/status events.
    """
    out = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for msg in value.get("messages", []) or []:
                if not isinstance(msg, dict):
                    continue
                sender = msg.get("from")
                mtype = msg.get("type")
                if not sender:
                    continue
                if mtype == "text":
                    body = (msg.get("text") or {}).get("body")
                    if body:
                        out.append({"from": sender, "kind": "text", "value": body})
                elif mtype == "interactive":
                    inter = msg.get("interactive") or {}
                    if inter.get("type") == "button_reply":
                        bid = (inter.get("button_reply") or {}).get("id")
                        if bid:
                            out.append({"from": sender, "kind": "button", "value": bid})
                # other message types (status, reactions, media) are ignored
    return out

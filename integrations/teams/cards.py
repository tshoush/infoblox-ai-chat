"""Adaptive Card builders for the Teams adapter (pure functions, testable).

No botbuilder import here so they can be unit-tested without the SDK.
"""
import json
from typing import Any, Dict, List

_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"


def _card(body: List[Dict[str, Any]], actions: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    card = {"type": "AdaptiveCard", "version": "1.4", "$schema": _SCHEMA, "body": body}
    if actions:
        card["actions"] = actions
    return card


def answer_card(text: str) -> Dict[str, Any]:
    body = text if len(text) <= 20000 else text[:20000] + "\n…(truncated)"
    return _card([{"type": "TextBlock", "text": body, "wrap": True}])


def denied_card(reason: str) -> Dict[str, Any]:
    return _card([{"type": "TextBlock", "text": f"⛔ {reason}", "wrap": True, "color": "Attention"}])


def proposal_card(operations: List[Dict[str, Any]], warnings: List[Dict[str, Any]],
                  token: str, ticket: str = None) -> Dict[str, Any]:
    n = len(operations)
    body: List[Dict[str, Any]] = [
        {"type": "TextBlock", "text": f"Proposed change — {n} WAPI call{'s' if n != 1 else ''}",
         "weight": "Bolder", "wrap": True},
    ]
    if ticket:
        body.append({"type": "TextBlock", "text": f"🎫 Change ticket: {ticket}", "wrap": True, "isSubtle": True})
    for i, op in enumerate(operations, 1):
        body.append({"type": "TextBlock", "fontType": "Monospace", "wrap": True,
                     "text": f"{i}. {op.get('method')} {op.get('operation')}"})
    if warnings:
        lines = [("🛑 " if w.get("level") == "danger" else "⚠️ ")
                 + f"Step {w.get('index', 0) + 1}: {w.get('message', '')}" for w in warnings]
        body.append({"type": "TextBlock", "text": "\n".join(lines), "wrap": True, "color": "Warning"})

    actions = [
        {"type": "Action.Submit", "title": "✅ Approve & Run", "style": "positive",
         "data": {"iaci_action": "run", "token": token}},
        {"type": "Action.Submit", "title": "Cancel", "style": "destructive",
         "data": {"iaci_action": "cancel", "token": token}},
    ]
    return _card(body, actions)


def results_card(operations: List[Dict[str, Any]], results: List[Dict[str, Any]],
                 approver: str) -> Dict[str, Any]:
    ok = sum(1 for r in results if r.get("success"))
    body = [{"type": "TextBlock", "weight": "Bolder", "wrap": True,
             "text": f"Executed {ok}/{len(operations)} call(s) — approved by {approver}"}]
    for op, res in zip(operations, results):
        tag = "✅" if res.get("success") else "❌"
        detail = json.dumps(res.get("data")) if res.get("success") else (res.get("error") or "failed")
        if len(detail) > 180:
            detail = detail[:180] + " …"
        body.append({"type": "TextBlock", "wrap": True,
                     "text": f"{tag} `{op.get('method')} {op.get('operation')}` — {detail}"})
    return _card(body)

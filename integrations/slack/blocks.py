"""Block Kit builders for the Slack adapter (pure functions, unit-testable).

Kept free of any slack_bolt import so they can be tested without the SDK.
"""
import json
from typing import List, Dict, Any


def _summary_line(op: Dict[str, Any]) -> str:
    return f"`{op.get('method')} {op.get('operation')}`"


def answer_blocks(text: str) -> List[Dict[str, Any]]:
    """A plain answer (read result / natural-language reply)."""
    # Slack section text caps at 3000 chars.
    body = text if len(text) <= 2900 else text[:2900] + "\n…(truncated)"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": body}}]


def proposal_blocks(operations: List[Dict[str, Any]], warnings: List[Dict[str, Any]],
                    token: str, ticket: str = None) -> List[Dict[str, Any]]:
    """An approval card: the plan, pre-flight warnings, and Approve/Cancel buttons."""
    n = len(operations)
    header = f"*Proposed change — {n} WAPI call{'s' if n != 1 else ''}*"
    if ticket:
        header += f"  ·  🎫 {ticket}"
    steps = "\n".join(f"{i+1}. {_summary_line(op)}" for i, op in enumerate(operations))

    blocks: List[Dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{header}\n{steps}"}},
    ]

    if warnings:
        lines = []
        for w in warnings:
            icon = "🛑" if w.get("level") == "danger" else "⚠️"
            lines.append(f"{icon} Step {w.get('index', 0) + 1}: {w.get('message', '')}")
        blocks.append({"type": "section",
                       "text": {"type": "mrkdwn", "text": "*Heads up:*\n" + "\n".join(lines)}})

    # The full plan as context (collapsed-ish); short JSON only.
    plan_json = json.dumps(operations)
    if len(plan_json) <= 2900:
        blocks.append({"type": "context",
                       "elements": [{"type": "mrkdwn", "text": f"```{plan_json}```"}]})

    blocks.append({
        "type": "actions",
        "block_id": f"iaci_approve::{token}",
        "elements": [
            {"type": "button", "style": "primary", "action_id": "iaci_run",
             "text": {"type": "plain_text", "text": "✅ Approve & Run"}, "value": token},
            {"type": "button", "style": "danger", "action_id": "iaci_cancel",
             "text": {"type": "plain_text", "text": "Cancel"}, "value": token},
        ],
    })
    return blocks


def results_blocks(operations: List[Dict[str, Any]], results: List[Dict[str, Any]],
                   approver: str) -> List[Dict[str, Any]]:
    """Post-execution summary with per-call ✅/❌ and who approved."""
    lines = []
    ok = 0
    for op, res in zip(operations, results):
        success = bool(res.get("success"))
        ok += success
        tag = "✅" if success else "❌"
        detail = json.dumps(res.get("data")) if success else (res.get("error") or "failed")
        if len(detail) > 180:
            detail = detail[:180] + " …"
        lines.append(f"{tag} {_summary_line(op)} — {detail}")
    head = f"*Executed {ok}/{len(operations)} call(s)* (approved by <@{approver}>)"
    return [{"type": "section", "text": {"type": "mrkdwn", "text": head + "\n" + "\n".join(lines)}}]


def denied_blocks(reason: str) -> List[Dict[str, Any]]:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f":no_entry: {reason}"}}]

"""IACI WhatsApp adapter (Meta Cloud API, Flask webhook).

Same core behavior as Slack/Teams. NOTE: WhatsApp identifies users only by phone
number and has limited interactivity, so it's the weakest platform for executing
changes — use it read-mostly, and keep WHATSAPP_WRITER_USERS tight.

Run:  python -m integrations.whatsapp.app          (listens on :8088)
Env:  WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID     (Meta Cloud API)
      WHATSAPP_VERIFY_TOKEN                         (your webhook verify string)
      IACI_API_URL, WHATSAPP_WRITER_USERS, WHATSAPP_ADMIN_USERS  (phone numbers)
Needs a public HTTPS webhook -> /webhook. See integrations/whatsapp/README.md.
"""
import hashlib
import hmac
import logging
import os

import requests
from flask import Flask, request

from integrations.core.iaci import IaciClient
from integrations.core.rbac import Rbac
from integrations.core.conversation import PendingStore, plan_for_message, run_approval
from integrations.core.change_ticket import TicketPolicy
from integrations.whatsapp import messages

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("iaci.whatsapp")

iaci = IaciClient()
rbac = Rbac.from_env("WHATSAPP")
tickets = TicketPolicy()
pending = PendingStore()

GRAPH = "https://graph.facebook.com/v19.0"
TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "iaci-verify")
APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "")

app = Flask(__name__)


def _valid_signature(raw: bytes, header: str) -> bool:
    """Verify Meta's X-Hub-Signature-256 (HMAC-SHA256 of the raw body).

    Fail-CLOSED when writers are configured but no app secret is set — a bot
    that can change the Grid must not accept unauthenticated webhooks."""
    if not APP_SECRET:
        if rbac.writers:
            log.error("WHATSAPP_APP_SECRET not set but writers are configured — rejecting webhook.")
            return False
        return True  # read-only deployment: allow (still verify-token gated)
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header[len("sha256="):])


def _send(message: dict):
    try:
        r = requests.post(f"{GRAPH}/{PHONE_ID}/messages",
                          headers={"Authorization": f"Bearer {TOKEN}"},
                          json=message, timeout=20)
        if not r.ok:
            log.warning("WhatsApp send failed %s: %s", r.status_code, r.text[:200])
    except requests.exceptions.RequestException as e:
        log.warning("WhatsApp send error: %s", e)


def _handle_text(sender: str, text: str):
    decision = plan_for_message(iaci, rbac, text, sender, session_id=sender, ticket_policy=tickets)
    kind = decision["kind"]
    if kind == "help":
        _send(messages.text_message(sender, "Ask me about your Infoblox Grid, e.g. “how many networks have no DHCP scope?”"))
    elif kind in ("answer", "error"):
        _send(messages.text_message(sender, decision["text"]))
    elif kind in ("denied", "needs_ticket"):
        _send(messages.text_message(sender, f"⛔ {decision['reason']}"))
    elif kind == "approval":
        token = pending.put(decision["operations"], sender, sender, ticket=decision.get("ticket"))
        _send(messages.approval_message(sender, decision["operations"], decision["warnings"], token,
                                        ticket=decision.get("ticket")))


def _handle_button(sender: str, button_id: str):
    action, _, token = button_id.partition(":")
    if action == "cancel":
        pending.take(token)
        _send(messages.text_message(sender, "❌ Change cancelled."))
        return
    item = pending.take(token)  # single-use -> idempotent
    if not item:
        _send(messages.text_message(sender, "That approval has expired or was already actioned."))
        return
    outcome = run_approval(iaci, rbac, item, sender)
    if not outcome["ok"]:
        _send(messages.text_message(sender, f"⛔ {outcome['reason']}"))
        return
    ok = sum(1 for r in outcome["results"] if r.get("success"))
    _send(messages.text_message(sender, f"Executed {ok}/{len(outcome['operations'])} call(s)."))
    log.info("AUDIT %s approved & ran %d op(s) [ticket=%s]: %s", sender,
             len(outcome["operations"]), outcome.get("ticket") or "none", outcome.get("summary"))


@app.route("/webhook", methods=["GET"])
def verify():
    # Meta webhook verification handshake.
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.route("/webhook", methods=["POST"])
def incoming():
    if not _valid_signature(request.get_data(), request.headers.get("X-Hub-Signature-256")):
        return "forbidden", 403
    payload = request.get_json(silent=True) or {}
    for msg in messages.parse_inbound(payload):
        if msg["kind"] == "text":
            _handle_text(msg["from"], msg["value"])
        elif msg["kind"] == "button":
            _handle_button(msg["from"], msg["value"])
    return "ok", 200  # always 200 so Meta doesn't retry-storm


def main():
    if not (TOKEN and PHONE_ID):
        raise SystemExit("WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID must be set. See integrations/whatsapp/README.md.")
    if not iaci.health():
        log.warning("IACI backend not reachable at %s — start it first.", iaci.base_url)
    log.info("Starting IACI WhatsApp bot on :%s (/webhook). Writers=%d Admins=%d",
             os.getenv("WHATSAPP_PORT", "8088"), len(rbac.writers), len(rbac.admins))
    app.run(host="0.0.0.0", port=int(os.getenv("WHATSAPP_PORT", "8088")))


if __name__ == "__main__":
    main()

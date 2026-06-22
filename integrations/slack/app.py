"""IACI Slack adapter (Socket Mode).

A thin front-end onto the IACI backend: answers Grid questions for everyone,
and turns change requests into an approval card (plan + pre-flight warnings +
Approve/Cancel buttons). Shared logic lives in integrations.core; this module
only renders Block Kit and wires Slack events.

Run:  python -m integrations.slack.app
Env:  SLACK_BOT_TOKEN (xoxb-…), SLACK_APP_TOKEN (xapp-…, Socket Mode),
      IACI_API_URL (default http://localhost:5050),
      SLACK_WRITER_USERS / SLACK_ADMIN_USERS, SLACK_AUDIT_CHANNEL (optional).
"""
import logging
import os
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from integrations.core.iaci import IaciClient
from integrations.core.rbac import Rbac
from integrations.core.conversation import PendingStore, plan_for_message, run_approval
from integrations.core.change_ticket import TicketPolicy
from integrations.slack import blocks

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("iaci.slack")

iaci = IaciClient()
rbac = Rbac.from_env("SLACK")
tickets = TicketPolicy()
pending = PendingStore()
AUDIT_CHANNEL = os.getenv("SLACK_AUDIT_CHANNEL")

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))


def _strip_mention(text: str) -> str:
    return re.sub(r"<@[^>]+>\s*", "", text or "").strip()


def _audit(client, text: str):
    log.info("AUDIT %s", text)
    if AUDIT_CHANNEL:
        try:
            client.chat_postMessage(channel=AUDIT_CHANNEL, text=text)
        except Exception as e:  # noqa: BLE001
            log.warning("Could not post to audit channel: %s", e)


def _handle(text: str, user: str, channel: str, thread_ts: str, client):
    decision = plan_for_message(iaci, rbac, text, user, session_id=thread_ts, ticket_policy=tickets)
    kind = decision["kind"]

    if kind == "help":
        client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                text="Ask me about your Infoblox Grid, e.g. “how many networks have no DHCP scope?”")
    elif kind in ("answer", "error"):
        client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                blocks=blocks.answer_blocks(decision["text"]), text="IACI")
    elif kind in ("denied", "needs_ticket"):
        client.chat_postMessage(channel=channel, thread_ts=thread_ts,
                                blocks=blocks.denied_blocks(decision["reason"]), text="Action required")
    elif kind == "approval":
        token = pending.put(decision["operations"], thread_ts, user, ticket=decision.get("ticket"))
        client.chat_postMessage(
            channel=channel, thread_ts=thread_ts,
            blocks=blocks.proposal_blocks(decision["operations"], decision["warnings"], token,
                                          ticket=decision.get("ticket")),
            text="Approval required for an Infoblox change")


@app.event("app_mention")
def on_mention(event, client):
    thread_ts = event.get("thread_ts") or event["ts"]
    _handle(_strip_mention(event.get("text", "")), event["user"], event["channel"], thread_ts, client)


@app.command("/infoblox")
def on_command(ack, command, client):
    ack()  # must ack within 3s; the work continues after.
    _handle(command.get("text", "").strip(), command["user_id"], command["channel_id"], None, client)


@app.action("iaci_run")
def on_run(ack, body, client):
    ack()
    token = body["actions"][0]["value"]
    approver = body["user"]["id"]
    channel, ts = body["channel"]["id"], body["message"]["ts"]

    item = pending.take(token)  # single-use -> idempotent
    if not item:
        client.chat_postMessage(channel=channel, thread_ts=ts,
                                text="That approval has expired or was already actioned.")
        return

    outcome = run_approval(iaci, rbac, item, approver)
    if not outcome["ok"]:
        client.chat_postMessage(channel=channel, thread_ts=ts,
                                blocks=blocks.denied_blocks(outcome["reason"]), text="Could not run")
        return

    client.chat_update(channel=channel, ts=ts, text="Executed",
                       blocks=blocks.results_blocks(outcome["operations"], outcome["results"], approver))
    _audit(client, f"<@{approver}> approved & ran {len(outcome['operations'])} op(s) "
                   f"requested by <@{item['requester']}> "
                   f"[ticket={outcome.get('ticket') or 'none'}]: {outcome.get('summary')}")


@app.action("iaci_cancel")
def on_cancel(ack, body, client):
    ack()
    pending.take(body["actions"][0]["value"])
    client.chat_update(channel=body["channel"]["id"], ts=body["message"]["ts"],
                       text="Cancelled", blocks=blocks.answer_blocks(":x: Change cancelled."))


def main():
    for var in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        if not os.environ.get(var):
            raise SystemExit(f"{var} is not set. See integrations/slack/README.md.")
    if not iaci.health():
        log.warning("IACI backend not reachable at %s — start it first.", iaci.base_url)
    log.info("Starting IACI Slack bot (Socket Mode). Writers=%d Admins=%d", len(rbac.writers), len(rbac.admins))
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()

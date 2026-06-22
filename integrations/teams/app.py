"""IACI Microsoft Teams adapter (Bot Framework, aiohttp).

A thin front-end onto the IACI backend, mirroring the Slack bot: answers Grid
questions, and renders changes as an Adaptive Card with Approve/Cancel. Shared
logic is in integrations.core; this module only renders cards and wires the Bot
Framework activity handler.

Run:  python -m integrations.teams.app           (listens on :3978)
Env:  MicrosoftAppId, MicrosoftAppPassword       (Azure Bot registration)
      IACI_API_URL, TEAMS_WRITER_USERS, TEAMS_ADMIN_USERS
Teams needs a public HTTPS messaging endpoint -> /api/messages (use a tunnel
like ngrok for local dev). See integrations/teams/README.md.
"""
import logging
import os

from aiohttp import web
from botbuilder.core import TurnContext, ActivityHandler, MessageFactory, CardFactory
from botbuilder.schema import ActivityTypes
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication

from integrations.core.iaci import IaciClient
from integrations.core.rbac import Rbac
from integrations.core.conversation import PendingStore, plan_for_message, run_approval
from integrations.core.change_ticket import TicketPolicy
from integrations.teams import cards

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("iaci.teams")

iaci = IaciClient()
rbac = Rbac.from_env("TEAMS")
tickets = TicketPolicy()
pending = PendingStore()


class _Config:
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")
    APP_TYPE = os.environ.get("MicrosoftAppType", "MultiTenant")
    APP_TENANTID = os.environ.get("MicrosoftAppTenantId", "")


class IaciTeamsBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        activity = turn_context.activity
        user = activity.from_property.id if activity.from_property else "unknown"
        session_id = activity.conversation.id if activity.conversation else None

        # An Adaptive Card Action.Submit arrives as a message with `value` set.
        value = activity.value if isinstance(activity.value, dict) else None
        if value and value.get("iaci_action"):
            await self._on_action(turn_context, value, user)
            return

        text = (activity.text or "").strip()
        decision = plan_for_message(iaci, rbac, text, user, session_id=session_id, ticket_policy=tickets)
        await self._render_decision(turn_context, decision, user, session_id)

    async def _render_decision(self, turn_context, decision, user, session_id):
        kind = decision["kind"]
        if kind == "help":
            await turn_context.send_activity("Ask me about your Infoblox Grid, e.g. “how many networks have no DHCP scope?”")
        elif kind in ("answer", "error"):
            await turn_context.send_activity(MessageFactory.attachment(
                CardFactory.adaptive_card(cards.answer_card(decision["text"]))))
        elif kind in ("denied", "needs_ticket"):
            await turn_context.send_activity(MessageFactory.attachment(
                CardFactory.adaptive_card(cards.denied_card(decision["reason"]))))
        elif kind == "approval":
            token = pending.put(decision["operations"], session_id, user, ticket=decision.get("ticket"))
            await turn_context.send_activity(MessageFactory.attachment(
                CardFactory.adaptive_card(cards.proposal_card(
                    decision["operations"], decision["warnings"], token, ticket=decision.get("ticket")))))

    async def _on_action(self, turn_context, value, approver):
        token = value.get("token")
        if value.get("iaci_action") == "cancel":
            pending.take(token)
            await turn_context.send_activity("❌ Change cancelled.")
            return
        item = pending.take(token)  # single-use -> idempotent
        if not item:
            await turn_context.send_activity("That approval has expired or was already actioned.")
            return
        outcome = run_approval(iaci, rbac, item, approver)
        if not outcome["ok"]:
            await turn_context.send_activity(MessageFactory.attachment(
                CardFactory.adaptive_card(cards.denied_card(outcome["reason"]))))
            return
        await turn_context.send_activity(MessageFactory.attachment(CardFactory.adaptive_card(
            cards.results_card(outcome["operations"], outcome["results"], approver))))
        log.info("AUDIT %s approved & ran %d op(s) [ticket=%s]: %s", approver,
                 len(outcome["operations"]), outcome.get("ticket") or "none", outcome.get("summary"))


ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(_Config()))
BOT = IaciTeamsBot()


async def messages(req: web.Request) -> web.Response:
    return await ADAPTER.process(req, BOT)


def main():
    if not iaci.health():
        log.warning("IACI backend not reachable at %s — start it first.", iaci.base_url)
    log.info("Starting IACI Teams bot on :3978 (POST /api/messages). Writers=%d Admins=%d",
             len(rbac.writers), len(rbac.admins))
    app = web.Application()
    app.router.add_post("/api/messages", messages)
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("TEAMS_PORT", "3978")))


if __name__ == "__main__":
    main()

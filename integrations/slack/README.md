# IACI Slack bot

A team front-end onto the IACI backend. Members ask the bot about the Grid in
plain English; changes come back as an **approval card** (plan + duplicate/
destructive warnings + Approve/Cancel buttons). Reads are open to the channel;
writes are gated by RBAC and audit-logged.

It uses **Socket Mode** — the bot dials out to Slack, so there's **no public
endpoint** (ideal since the Grid is internal).

## 1. Create the Slack app
1. https://api.slack.com/apps → **Create New App → From scratch**.
2. **Socket Mode** → enable → create an **App-Level Token** with scope
   `connections:write` → copy `xapp-…` → `SLACK_APP_TOKEN`.
3. **OAuth & Permissions → Bot Token Scopes**: `app_mentions:read`, `chat:write`,
   `commands`, `users:read`. Install to workspace → copy `xoxb-…` → `SLACK_BOT_TOKEN`.
4. **Event Subscriptions** (Socket Mode) → subscribe to bot event `app_mention`.
5. **Slash Commands** → create `/infoblox` (any request URL; Socket Mode ignores it).
6. Invite the bot to a channel: `/invite @YourBot`.

## 2. Configure
Add to `.env` (or the bot's environment):
```
SLACK_BOT_TOKEN=xoxb-…
SLACK_APP_TOKEN=xapp-…
IACI_API_URL=http://localhost:5050
SLACK_WRITER_USERS=U0123,U0456     # Slack user IDs allowed to approve changes
SLACK_ADMIN_USERS=U0123            # may also approve DELETEs (destructive)
SLACK_AUDIT_CHANNEL=C0AUDIT        # optional: mirror executions here
```
> Find a user ID: click a profile → ⋮ → *Copy member ID*. No writers configured =
> the bot answers questions but refuses every change (fail-closed).

## 3. Run
```
./setup.sh slack            # installs deps, checks tokens, starts the bot
# or manually:
pip install -r integrations/slack/requirements.txt
python -m integrations.slack.app
```

## Usage
- `@IACI how many networks have no DHCP scope?` → answered inline.
- `@IACI create network 10.9.0.0/24 with a DHCP scope and gateway .1`
  → approval card. An authorized user clicks **Approve & Run** → it executes and
  the card updates with ✅/❌ results and who approved.

## Safety model
- Reads: open. Writes: `SLACK_WRITER_USERS`. Deletes: `SLACK_ADMIN_USERS`.
- The **approver** (button clicker) is re-checked, not just the requester.
- Approvals are **single-use** (idempotent — a duplicate click does nothing).
- Pre-flight warnings (duplicate create / destructive delete) show before you run.
- Every execution is logged and can mirror to an audit channel.

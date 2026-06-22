# IACI Microsoft Teams bot

Same behavior as the Slack bot (answers + approval cards with pre-flight
warnings + Approve/Cancel), built on the Bot Framework. Unlike Slack, Teams
needs a **public HTTPS messaging endpoint** (`/api/messages`).

## 1. Register the bot (Azure)
1. Azure Portal → **Azure Bot** resource (or **App Registration** → multi-tenant).
2. Copy the **App ID** and create a **client secret** → `MicrosoftAppId` / `MicrosoftAppPassword`.
3. **Channels → Microsoft Teams** → enable.
4. Set the bot's **Messaging endpoint** to `https://<your-public-host>/api/messages`.
5. Build a Teams app package (App Studio / Developer Portal) referencing the bot, and side-load it to your team.

## 2. Configure
```
MicrosoftAppId=...
MicrosoftAppPassword=...
IACI_API_URL=http://localhost:5050
TEAMS_WRITER_USERS=29:1abc...      # Teams/AAD user IDs allowed to approve changes
TEAMS_ADMIN_USERS=29:1abc...       # may also approve DELETEs
```
> Find a user id from the incoming activity (`from.id`) — log one message, or use
> the Developer Portal. No writers configured = answers only, all changes refused.

## 3. Run + expose
```
./setup.sh teams                     # installs deps, starts the bot on :3978
ngrok http 3978                      # (or any tunnel) -> use the https URL as the messaging endpoint
```
For local testing without Teams, use the **Bot Framework Emulator** pointed at
`http://localhost:3978/api/messages`.

## Safety model
Identical to Slack: reads open, writes need `TEAMS_WRITER_USERS`, DELETE needs
`TEAMS_ADMIN_USERS`; the approver is re-checked; approvals are single-use
(idempotent); pre-flight duplicate/destructive warnings shown before running.

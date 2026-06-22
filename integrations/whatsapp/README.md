# IACI WhatsApp bot

Same core behavior as Slack/Teams (answers + approval with Approve/Cancel reply
buttons + pre-flight warnings), via the **Meta WhatsApp Cloud API**.

> ⚠️ WhatsApp identifies users only by phone number and has limited
> interactivity — it's the weakest platform for *executing* changes. Prefer it
> read-mostly and keep `WHATSAPP_WRITER_USERS` tight.

## 1. Set up the Cloud API (Meta)
1. https://developers.facebook.com → create an app → add **WhatsApp**.
2. Note the **Phone number ID** and a **permanent access token** →
   `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_TOKEN`.
3. **Configuration → Webhook**: callback URL `https://<public-host>/webhook`,
   verify token = your `WHATSAPP_VERIFY_TOKEN`; subscribe to the **messages** field.

## 2. Configure
```
WHATSAPP_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=10987654321
WHATSAPP_VERIFY_TOKEN=some-secret-string
IACI_API_URL=http://localhost:5050
WHATSAPP_WRITER_USERS=15551234567      # phone numbers (wa_id) allowed to approve
WHATSAPP_ADMIN_USERS=15551234567       # may also approve DELETEs
```

## 3. Run + expose
```
./setup.sh whatsapp                    # installs deps, starts the webhook on :8088
ngrok http 8088                        # (or any tunnel) -> use the https URL in the Meta webhook config
```

## Safety model
Reads open; writes need `WHATSAPP_WRITER_USERS`; DELETE needs `WHATSAPP_ADMIN_USERS`.
Approvals are single-use (idempotent against Meta's webhook retries). Pre-flight
duplicate/destructive warnings are shown before running.

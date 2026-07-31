# Email Sending Service (Phase 6)

## Guarantees (enforced in `app/sender/service.py`, the only send path)

1. **Suppression wins.** Unsubscribed/bounced addresses are checked at send
   time; a queued draft to a suppressed address is rejected, never sent.
2. **Caps are DB-counted** (`email_messages` in the last 24h/1h), so process
   restarts cannot reset them. Defaults: 25/day, 10/hour (warm-up safe);
   raise via `DAILY_SEND_CAP` / `HOURLY_SEND_CAP` as reputation builds.
3. Only `APPROVED` drafts are eligible; failed sends stay `APPROVED` for retry.
4. First-touch sends schedule follow-ups at day 3/7/14; any bounce or
   unsubscribe cancels the pending sequence and suppresses the address.
5. Every email carries a signed per-contact unsubscribe link
   (`/u/<id>.<hmac>`, verified without DB state, unforgeable without the
   app secret).

## Providers

`EmailSenderProvider` protocol; v1 ships `SMTPSender` (STARTTLS + login),
which covers Brevo, Zoho, and any standard relay. Gmail API / Microsoft Graph
adapters slot in later without touching the service.

## Go-live checklist (your custom domain)

1. Create the sending mailbox — recommended on a subdomain:
   `outreach.<yourdomain>` (protects the root domain's reputation).
2. DNS records (your relay's dashboard gives exact values):
   - SPF: `v=spf1 include:<relay-spf> ~all`
   - DKIM: CNAME/TXT keys from the relay
   - DMARC: `v=DMARC1; p=quarantine; rua=mailto:dmarc@<yourdomain>`
3. Fill `backend/.env`:
   ```
   SMTP_HOST=smtp-relay.brevo.com   # or smtp.zoho.in
   SMTP_PORT=587
   SMTP_USERNAME=...
   SMTP_PASSWORD=...
   SENDER_NAME=Maaz Patel
   SENDER_EMAIL=maaz@outreach.<yourdomain>
   SENDER_POSTAL_ADDRESS=<street, city, PIN>   # required footer line
   PUBLIC_BASE_URL=https://<deployed-api-host>
   DAILY_SEND_CAP=25
   ```
4. Send a test to yourself, check SPF/DKIM/DMARC pass in the received
   headers (Gmail: "Show original").
5. Warm-up: keep 25/day for week 1, then +25/week while bounce rate < 2%
   and no spam-folder reports.

## CLI

```powershell
python -m app.cli send --dry-run      # show quota + queued approved drafts
python -m app.cli send --limit 5      # send within caps
```

Bounce intake (`record_bounce`) and the public unsubscribe endpoint are wired
to HTTP routes in Phase 7 (API); the service functions are complete and tested.

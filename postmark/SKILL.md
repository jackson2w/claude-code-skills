---
name: postmark
description: This skill should be used when the user asks to "send email via Postmark", "set up Postmark", "configure an SMTP relay with Postmark", "check Postmark delivery status", "use my Postmark account", or needs transactional email sending/delivery verification through Postmark's SMTP relay or HTTP API — including from non-Workers systems like Proxmox, cron jobs, or backend services that support a generic SMTP smarthost.
---

# Postmark

Postmark sends transactional email over an authenticated SMTP relay or HTTP API, and exposes delivery status through the same API — use it whenever a system needs outbound email that must actually land in the inbox rather than direct-from-origin SMTP, which unauthenticated senders (residential IPs, ad hoc hostnames with no SPF/DKIM) get spam-filtered on almost immediately.

## Message streams — pick the right one

Every Postmark server has (at minimum) three message streams, visible under Servers → *server name* → Message Streams:

| Stream | Stream ID | Use for |
|---|---|---|
| Default Transactional Stream | `outbound` | One-to-one, system- or app-generated email: alerts, receipts, password resets, backup/job notifications. **Default choice for almost everything.** |
| Default Broadcast Stream | (custom ID) | Bulk/marketing sends to many recipients at once. Requires unsubscribe handling. Never use for system notifications. |
| Default Inbound Stream | `inbound` | Receiving mail routed to Postmark, not sending. Irrelevant for sending tasks. |

Note the Transactional stream's actual ID is literally `outbound` despite the UI label "Transactional" — this shows up in API responses (`"MessageStream": "outbound"`) and is correct, not a sign something is misconfigured.

## Prerequisite: verified sender

Postmark rejects any send whose `From` address isn't a verified Sender Signature (single address) or a verified Domain in that account. Before configuring anything, confirm with the user which address/domain is verified (Settings → Sender Signatures / Domains) — don't guess a `From` address.

## SMTP relay setup

For any system that supports a generic SMTP smarthost (Postfix `relayhost`, Proxmox's notification `smtp` endpoint type, application mailer configs, etc.), point it at Postmark directly instead of routing through local Postfix/sendmail with no authentication:

- Server: `smtp.postmarkapp.com`
- Port: `587` with STARTTLS (recommended default); `465` for implicit TLS; `25` plaintext only if the platform has no other option
- **Auth quirk**: username and password are **both the same value** — the Server API Token (a UUID, found under the server's API Tokens tab). This trips people up because it looks like it should be a separate username/password pair; it isn't.
- `From` address: must be the verified sender confirmed above.

This is the standard fix when a system is sending real mail that lands in spam: the root cause is almost always missing sender authentication (no SPF/DKIM/DMARC alignment for the sending domain, or direct delivery from an IP with no matching reverse DNS), not email content or formatting. Routing through Postmark (or any authenticated relay) fixes deliverability at the transport layer; polishing subject lines/body content afterward is a separate, smaller improvement.

## Sending via the HTTP API from a bash script

For a script that needs to email a large or dynamic body (a generated report, log tail, etc.)
rather than a fixed short string, use `POST /email` with the body built via `jq` rather than
hand-escaping the JSON — `jq --rawfile` reads the body from a file and handles newline/quote
escaping correctly, which matters once the content is more than a one-liner:

```bash
payload=$(jq -n \
  --arg from "$POSTMARK_FROM" \
  --arg to "$POSTMARK_TO" \
  --arg subject "Report - $(date +%F)" \
  --rawfile body /path/to/report.md \
  '{From:$from, To:$to, Subject:$subject, TextBody:$body, MessageStream:"outbound"}')

curl -s "https://api.postmarkapp.com/email" \
  -X POST \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -H "X-Postmark-Server-Token: <server-api-token>" \
  -d "$payload"
```

A successful response is JSON with `"ErrorCode":0` and a real `MessageID` — check for that
directly rather than just trusting a non-error exit code from `curl` (which only confirms the
HTTP request itself completed, not that Postmark accepted the message).

## Verifying delivery via the HTTP API

The same Server API Token doubles as the HTTP API credential — don't assume a message was actually delivered just because SMTP accepted it (a `250 OK` from the relay only means it was queued, not delivered). Confirm via the API instead:

```bash
# List recent outbound sends
curl -s "https://api.postmarkapp.com/messages/outbound?count=5&offset=0" \
  -H "Accept: application/json" \
  -H "X-Postmark-Server-Token: <server-api-token>"

# Pull the full rendered body/headers for one message (useful for debugging
# template rendering, checking the exact From/Subject that went out, etc.)
curl -s "https://api.postmarkapp.com/messages/outbound/<MessageID>/details" \
  -H "Accept: application/json" \
  -H "X-Postmark-Server-Token: <server-api-token>"
```

Check the `Status` field (`"Sent"` is the expected success state). A newly-sent message can take several seconds to appear in the outbound list — if a just-sent message isn't showing up yet, retry once or twice a few seconds apart before concluding something failed; don't treat an empty/stale-looking result as an immediate failure signal.

## Common integration pattern: system-level notification relays

Many platforms (Proxmox VE's built-in notification system, cron-triggered scripts, backup tools) support configuring an external SMTP target for their own alerting, separate from whatever the OS's local mail transport agent does. Prefer wiring Postmark in at that layer — e.g. Proxmox exposes `pvesh create /cluster/notifications/endpoints/smtp --server smtp.postmarkapp.com --port 587 --mode starttls --username <token> --password <token> --from-address <verified-address> --author "<display name>" --mailto <recipient>` — rather than reconfiguring the underlying OS mail transport agent (Postfix, etc.), which affects all system mail, not just the one notification path that needed fixing.

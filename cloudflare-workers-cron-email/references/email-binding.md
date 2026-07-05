# `send_email` binding: config and API reference

## wrangler.toml / wrangler.jsonc syntax

```toml
[[send_email]]
name = "EMAIL"
# No destination_address: binding can send to any verified destination
# address in the account.

[[send_email]]
name = "NOTIFY_OPS"
destination_address = "ops@yourdomain.com"
# Restricts this binding to a single fixed recipient — a good safety rail
# for a single-purpose notification Worker.

[[send_email]]
name = "EMAIL_TEAM"
allowed_destination_addresses = [ "alice@yourdomain.com", "bob@yourdomain.com" ]
# Allowlist of permitted recipients.

[[send_email]]
name = "RESTRICTED_EMAIL"
allowed_sender_addresses = [ "noreply@yourdomain.com", "support@yourdomain.com" ]
# Allowlist of permitted senders.
```

JSONC equivalent:

```jsonc
{
  "send_email": [
    { "name": "EMAIL" },
    { "name": "NOTIFY_OPS", "destination_address": "ops@yourdomain.com" },
    { "name": "EMAIL_TEAM", "allowed_destination_addresses": ["alice@yourdomain.com", "bob@yourdomain.com"] },
    { "name": "RESTRICTED_EMAIL", "allowed_sender_addresses": ["noreply@yourdomain.com"] }
  ]
}
```

## Runtime API: `env.<BINDING>.send()`

Structured send — no `mimetext`/`EmailMessage` construction needed for
typical use (that's the older/legacy pattern; prefer this one for new code):

```js
const response = await env.EMAIL.send({
  to: "recipient@example.com",
  from: "sender@yourdomain.com",           // or { email, name } for a display name
  subject: "Subject line",
  html: "<h1>...</h1>",                     // optional
  text: "plain text fallback",              // optional
  cc: "cc@example.com",                     // optional, string | EmailAddress | array
  bcc: "bcc@example.com",                   // optional
  replyTo: "reply@example.com",             // optional
  attachments: [ /* Attachment[] */ ],      // optional
  headers: { "X-Custom": "value" },         // optional
});
// response.messageId
```

`to`/`from`/`cc`/`bcc` each accept `string | EmailAddress | (string|EmailAddress)[]`.
`EmailAddress` shape: `{ email: string, name?: string }` — use this to set a
friendly display name for the sender (e.g. `{ email: "backup@x.com", name: "Backup Bot" }`).

Combined `to` + `cc` + `bcc` addresses must not exceed 50.

`Attachment` shape: `{ content: string | ArrayBuffer | ArrayBufferView, filename: string, type: string, disposition: "attachment" | "inline", contentId?: string }`.

## The two domain requirements, and why they're different

1. **`from` domain** needs Cloudflare Email Routing enabled as a zone (DNS on
   Cloudflare, MX/SPF/DKIM records Cloudflare manages) — this is what lets
   Cloudflare authenticate mail sent *from* an address on that domain.

2. **Destination address** (`to`, or `destination_address` in the binding)
   verification is **account-level**, entirely separate from #1. Add it via
   the dashboard: Email → Email Routing → Destination Addresses → Add →
   Cloudflare emails a confirmation link to that address → click it. This
   works for literally any inbox — a personal Gmail, an address on a domain
   with unrelated email hosting, anything — because Cloudflare only needs to
   confirm you can read that inbox, not route mail to it. No MX or DNS change
   happens on the destination's domain.

A clean pattern that avoids ever touching a domain's real MX records: pick a
spare/unused domain purely as the `from` zone (enable Email Routing there,
nothing else lives on it), and set the destination address to wherever the
human actually reads mail (their real personal address), verified via the
account-level flow above.

## Common failure modes

| Error | Cause | Fix |
|---|---|---|
| `destination address is not a verified address` | The `to` address hasn't completed account-level verification | Add + verify it under Email Routing → Destination Addresses |
| Email silently doesn't arrive, no error | Often a spam-filtering issue or a `from` domain missing DKIM (Email Routing not actually enabled on that zone) | Confirm Email Routing status on the `from` domain in the dashboard |
| Deploy succeeds but binding shows wrong resource in `wrangler deploy` output | Stale `wrangler.toml` — the deploy output always echoes the actual bound resource; use it to sanity-check `destination_address` before troubleshooting further | Re-read the deploy output bindings table |

Sending to a verified destination address is free on every plan (Free and
Paid) and does not count toward any Email Sending quota.

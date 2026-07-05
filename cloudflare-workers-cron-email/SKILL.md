---
name: cloudflare-workers-cron-email
description: This skill should be used when the user asks to debug a Cloudflare Workers Cron Trigger that "isn't firing" or "not running" (or fires on the wrong day), set up or troubleshoot the send_email binding or Email Routing destination addresses for Workers, size a Worker against Cloudflare's per-invocation subrequest limits, test a scheduled() handler locally against real R2/KV/email bindings, verify an R2 delete/rename actually took effect, or rename/reorganize keys in an R2 bucket. Trigger phrases include "cron trigger not firing", "scheduled worker not running", "cron ran on the wrong day", "wrangler cron", "cron trigger debug", "send_email binding", "Workers email binding", "Email Routing destination address", "workers subrequest limit", "test-scheduled --remote", "r2 object rename", "r2 delete not working", "r2 move objects".
version: 0.2.0
---

# Cloudflare Workers: Cron Triggers + Email Bindings

Diagnose scheduled Cloudflare Workers that silently fail to run, size a Worker's
R2/KV workload against subrequest limits before it's built, and wire up the
`send_email` binding correctly the first time. This knowledge comes from a real
debugging session where a correctly-configured cron trigger and a correctly-coded
Worker both looked broken for reasons that took real investigation to isolate.

## Core principle: distrust `wrangler tail` for "did it run?"

`wrangler tail` can attach to a stale or reused session and replay old log
lines instead of showing genuinely new activity — it produced byte-identical
output (down to the same historical timestamp) across two separate invocations
during testing, several minutes apart, while a cron trigger was firing on a
2-minute schedule. Treat `wrangler tail` as useful for *watching* a Worker
interactively, never as the ground truth for "has this invocation happened."

For ground truth, use two Cloudflare APIs instead:

1. **Is the schedule registered?**
   `GET /accounts/{account_id}/workers/scripts/{script_name}/schedules`
   Returns the cron pattern and `created_on`/`modified_on` timestamps. See
   `scripts/check-schedule-registered.sh`.

2. **Has it actually invoked?**
   The GraphQL Analytics API's `workersInvocationsAdaptive` dataset, filtered
   by `scriptName` and a datetime range, returns real invocation counts
   (`sum.requests`, `sum.errors`) per time bucket — independent of tail,
   independent of the dashboard's "Requests" tile (which does reflect cron
   invocations, but only after they've happened). See
   `scripts/check-cron-invocations.sh`. Full query template in
   `references/diagnosing-cron.md`.

## GraphQL Analytics has real ingestion lag — do not conclude "broken" too early

Live-polling `workersInvocationsAdaptive` every 30s for 10+ minutes showed a
flat, unchanging invocation count while a 2-minute cron was, in fact, firing
correctly the entire time — confirmed after the fact by both a *later* query
against the same time window (which then showed every 2-minute tick present)
and by finding real copied output in the target R2 bucket from those runs.
The analytics pipeline had not finished ingesting recent minutes yet, and a
flat "stuck" count during live polling looks identical to a genuinely broken
dispatcher. **Do not conclude the cron dispatcher is broken from a live
polling session alone, no matter how long you wait** (10-15+ minutes of flat
zero is not conclusive) — instead, check for a real side effect of the job
(a new/changed object in the target bucket, a row in a database, etc.), or
re-run the same GraphQL query later, after stepping away, to let ingestion
catch up.

Separately, multiple Cloudflare Community threads *do* document real cases
where Cron Triggers register (visible via `/schedules`) but genuinely never
invoke `scheduled()` at all, with no error anywhere and no fix from
redeploying. That failure mode exists — but distinguish it from analytics lag
by checking for real side effects before concluding the dispatcher itself is
broken, not just by an unchanging analytics count. This section is time-bound
either way — re-verify before treating either claim as current fact.

## Testing `scheduled()` directly, bypassing the cron dispatcher entirely

`wrangler dev --test-scheduled --remote` exposes a local `/__scheduled` route
that invokes the Worker's `scheduled()` handler directly against its real
bound resources (R2, KV, email, etc.), without going through Cloudflare's cron
dispatcher at all. This is the fastest way to prove the *code* is correct,
independent of whether the dispatcher is currently reliable.

```bash
npx wrangler dev --test-scheduled --remote --port 8787 &
curl "http://localhost:8787/__scheduled?cron=0+9+*+*+1"
```

**Ceiling:** this tunnel has an effective ~90-120 second limit before it fails
with a 502/504, even though a real deployed cron invocation gets up to 15
minutes wall-clock. A job that legitimately needs longer than that (e.g., a
full-corpus R2 sync over many hundreds of objects) will fail here every time,
for reasons unrelated to correctness — do not keep retrying the same
full-scope test expecting a different result.

**Workaround:** temporarily scope the operation down so the test completes in
seconds — e.g., add a `prefix` filter to an R2 `list()` call, or limit to one
small subset of the real workload — to get a fast, decisive pass/fail signal
against real bindings. Mark the temporary change clearly in the code (e.g. a
`// TEMP test scope — revert before final deploy` comment) and track it
explicitly; it is easy to leave a test-only schedule or scope change live
through several redeploy cycles. Do a final review of the diff before the
production deploy to confirm every temporary knob was reverted.

## Cron Trigger day-of-week is 1=Sunday..7=Saturday, not the Unix convention

Cloudflare's cron day-of-week field runs **1=Sunday through 7=Saturday** —
different from standard Unix cron (where 0 or 7 = Sunday, 1 = Monday). A
schedule written as `0 9 * * 1` intending "Monday 9am" is actually "Sunday
9am" on Cloudflare, and will fire a day early with no error anywhere — it's a
silent semantic mismatch, not a bug in the dispatcher. Confirmed via a real
case: a backup Worker's `wrangler.toml` had `crons = ["0 9 * * 1"]` commented
"Weekly, Monday 09:00 UTC", and R2 snapshot object dates it wrote each run
proved it was actually firing every Sunday.

**Use the three-letter form (`MON`, `TUE`, `SUN`, ...) instead of a numeric
day-of-week** — Cloudflare's own docs recommend this specifically to avoid
the ambiguity. Verify the fix took effect with
`scripts/check-schedule-registered.sh` (or the dashboard's Triggers →
Settings tab, which shows a human-readable "Schedule: ... Next: ..." line —
note there's no manual "run now" button there, only edit/delete; see the
"Testing `scheduled()` directly" section above for how to actually fire it
on demand).

## R2 deletes/renames: HEAD/GET can lag, but the objects-list endpoint doesn't

Renaming or reorganizing keys in an R2 bucket means copy-then-delete for
every object — **R2 has no move/rename command**, only
`wrangler r2 object get/put/delete` (or the equivalent API calls) per key.

After deleting an object, a direct `HEAD`/`GET` on that same key (via
`wrangler r2 object get` or the REST API) can keep returning 200 + the old
body for **15+ seconds** after both the CLI and a direct API `DELETE` report
success — this looks exactly like the delete silently failing. It isn't: the
bucket's **objects-list endpoint**
(`GET /accounts/{account_id}/r2/buckets/{bucket}/objects?prefix=...`)
reflects the true state immediately and consistently on repeat queries, even
while HEAD/GET is still lagging. **When verifying a bulk delete or rename,
check with a prefix list, not a single HEAD/GET** — the same
"don't trust one check, verify with a real side effect" principle as the
cron-invocation guidance above, just for R2 instead of cron.

## Sizing a Worker against subrequest limits (do this before writing the loop)

Any Worker that loops over R2/KV objects (list, then get/head/put per object)
burns subrequests fast. Check the budget before designing the operation, not
after it fails in production:

| Plan | Subrequests / invocation | Cron CPU time | Wall-clock (scheduled) |
|---|---|---|---|
| Free | 50 | 10ms | 15 min (shared cap) |
| Paid ($5/mo base) | 10,000 | 30s (<1hr interval) / 15min (≥1hr interval) | 15 min |

Estimate: `object_count × ops_per_object` (a get+put pair is 2; add a `head`
for change-detection and it's 3). A few hundred objects at 3 ops each already
exceeds the free tier's 50-subrequest cap. If the estimate exceeds 50,
Workers Paid is required — this is a real, non-optional cost tradeoff to
surface to the user before building, not after deploying and hitting a wall.

## `send_email` binding facts (get these right the first time)

Full wrangler config syntax and API shape in `references/email-binding.md`.
The two facts that are easy to get backwards:

- **`from` address**: must be on a domain (zone) that has Cloudflare **Email
  Routing enabled** — Cloudflare needs that zone's SPF/DKIM records to
  authenticate outgoing mail. This is the only place DNS/MX matters.
- **Destination address** (the `to`): verification is **account-level** and
  fully independent of that address's own domain DNS. Add it under Email
  Routing → Destination Addresses; Cloudflare emails a confirmation link;
  clicking it verifies the address. No MX/Email Routing changes are needed on
  the destination domain at all — it can be a Gmail address, a personal
  domain with unrelated email hosting, anything.

Because enabling Email Routing on a zone rewrites its MX/SPF/DKIM records, do
not enable it on a domain that already has live email service without
explicit confirmation — prefer a spare/unused domain dedicated to outbound
Worker sending, and point the destination address at wherever the human
actually reads mail (their real personal address), using the account-level
verification above. Sending to a verified destination address is free on
every plan and does not count toward quota.

## Quick diagnostic checklist

When "the scheduled job isn't producing its expected output" (email, sync,
etc.), work through in this order:

1. Confirm the schedule is registered (`scripts/check-schedule-registered.sh`).
2. Look for a real side effect of the job (a new/changed object in the target
   bucket, etc.) — this is more conclusive than any analytics query, since
   analytics can lag by many minutes.
3. If no side effect and `scripts/check-cron-invocations.sh` shows zero, wait
   longer and re-query rather than trusting a single live-polling session —
   ingestion lag alone can produce a flat "stuck" reading that looks
   identical to a genuinely broken dispatcher. Do not stop at `wrangler tail`
   silence either; it can replay a stale session instead of showing nothing.
4. Only after a real side-effect check plus a delayed re-query both come back
   empty, suspect the platform-level dispatcher issue described above.
5. Independently verify the code path directly via `--test-scheduled --remote`
   with a scoped-down operation size — this bypasses the dispatcher and
   analytics lag entirely, and is the fastest way to isolate "is it the code
   or the platform."
6. If that also fails, check the subrequest budget against the plan tier.
7. If email specifically fails with "destination address is not a verified
   address", that's the account-level verification step, not a DNS/config
   bug — and don't assume a prior "yes it's verified" from a human is
   necessarily accurate; the error message is ground truth.

## Additional resources

- **`references/diagnosing-cron.md`** — full GraphQL Analytics query
  template, `/schedules` API details, and how to read the results.
- **`references/email-binding.md`** — wrangler.toml/jsonc `send_email`
  syntax variants (`destination_address`, `allowed_destination_addresses`,
  `allowed_sender_addresses`), the structured `env.EMAIL.send()` API shape,
  and the `EmailAddress` object form for a display name.
- **`scripts/check-schedule-registered.sh`** — curl wrapper for the
  `/schedules` endpoint.
- **`scripts/check-cron-invocations.sh`** — curl+GraphQL wrapper that prints
  total invocation count for a script over a given time range.

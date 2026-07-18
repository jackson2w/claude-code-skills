---
name: cloudflare-worker-tailscale-shield
description: This skill should be used when building a Cloudflare Worker that sits in front of a homelab service reachable only via Tailscale Funnel — validating auth/rate-limiting at Cloudflare's edge before forwarding inward, with a Cloudflare Queue for retry-on-failure. Also covers a specific `wrangler secret put` misuse that leaks the secret value as the secret's *name*. Trigger phrases include "cloudflare worker in front of tailscale", "webhook shield worker", "worker forward to tailscale funnel", "workers can't reach tailnet", "wrangler secret put wrong name", "queue retry backoff worker", "workers_dev false no public url".
---

# Cloudflare Worker fronting a Tailscale Funnel service (webhook-shield pattern)

First built 2026-07-18 for `n8n-webhook-shield` in the `homelab` repo: a public Worker in front
of n8n's Krisp webhook, validating auth + rate-limiting at Cloudflare's edge before forwarding
to n8n over its existing Tailscale Funnel. Generalizes to any "put a Worker in front of a
Tailscale-exposed homelab service" project.

## The core constraint: Workers can't reach tailnet-private addresses

Cloudflare Workers run on Cloudflare's edge network, not inside your tailnet. A Worker can only
reach a homelab service via a URL that's **actually publicly resolvable and reachable** — i.e.
the target's Tailscale **Funnel** URL, never a Serve-only (tailnet-private) one. This means a
plain Worker genuinely cannot "take a service off the public internet entirely" while still
being able to reach it — that requires a Cloudflare Tunnel connector running inside the
homelab instead (a separate, larger project). Confirm this tradeoff with whoever's asking for
the shield *before* building — the "n8n off the public internet" framing in an initial ask may
not be fully achievable with a Worker alone, and that's worth surfacing rather than silently
building something that doesn't match the stated goal.

What a Worker-in-front **does** genuinely deliver: the origin's Funnel URL becomes
double-gated (edge check + the origin's own existing auth), bad/abusive requests get rejected
before ever reaching home bandwidth, and a Cloudflare Queue can retry delivery through a brief
origin outage instead of silently dropping the event.

## `workers_dev` defaults matter differently for a public-facing vs. queue-consumer Worker

If templating off a cron-only or queue-only Worker (no real HTTP entry point), don't copy its
`"workers_dev": false` setting blindly into a *new* Worker that needs to actually receive public
HTTP traffic — that setting with no custom route configured means the Worker has **no public
URL at all**. Set `"workers_dev": true` for anything that needs a reachable `*.workers.dev` URL
(or configure a custom route/domain instead).

## The Worker must forward the origin's own auth header too, not just validate it

If the origin (e.g. n8n's webhook node) has its own independent auth check that's being kept as
a second layer (rather than removed in favor of the edge check), the Worker's forward `fetch()`
call must include that same auth header — it's easy to write a shield that validates the
inbound header but then constructs the outbound request with only `Content-Type`, forgetting to
carry the header through. The origin then rejects *everything* with its own 403/401 regardless
of whether the Worker's own check passed, and — this is the trap — **the caller sees no sign of
this at all**, because a well-designed shield returns `200` on both "delivered live" and
"queued for retry" (so the initial caller isn't punished for the origin being briefly down).
`curl`-checking only the shield's own HTTP status will never catch this bug.

**Verify with `wrangler tail` against the Worker actually receiving the origin's response**, not
just the status code the shield hands back to its caller. Add explicit logging distinguishing
"forwarded live" vs. "queued for retry" vs. the origin's actual response status/error — cheap to
add, and the only way to see this class of bug without guessing.

## Testing the queue/retry/alert path without waiting out the real backoff

If the retry consumer's give-up threshold is high (e.g. 8 attempts with exponential backoff
capped at 30 minutes), waiting for a genuine end-to-end exhaustion test takes ~30+ minutes.
Temporarily lower the threshold (e.g. to 3) for a test pass, point the shield at a deliberately
unreachable path so requests genuinely fail, confirm the alert fires, then **restore the real
threshold and redeploy** before considering the test done. Remember any messages already queued
during earlier failed tests (e.g. from a bug fixed mid-session) are independent, already-enqueued
messages with their own accumulated attempt counts — they'll keep failing under whatever bug
queued them and will each eventually alert-and-purge on their own schedule, which can look like
unexplained extra retries/alerts if you've forgotten they're sitting there from an earlier test.

## Rate limiting needs a real burst to test, not a quick sequential loop

Cloudflare's Workers `ratelimit` binding is explicitly documented as "permissive, eventually
consistent, and intentionally designed to not be used as an accurate accounting system" — a
tight sequential loop of even 25-60 requests from one location can all land within the
eventually-consistent window and pass through with no `429` at all, even though the binding is
configured and working correctly. This isn't a bug to chase. To actually observe a `429`,
generate real concurrent load (e.g. `seq 1 150 | xargs -P 40 -I{} curl ...`), not a for-loop.

## `wrangler secret put` misuse can leak the secret as the resource *name*

`wrangler secret put NAME` is meant to be run with **just the secret's name as the argument**,
then the value is entered at the interactive prompt it opens. If it's instead run as
`wrangler secret put "<the actual value>"` — passing the value where the name goes — the value
itself becomes the **name** of a new Cloudflare secret, which is then visible via `wrangler
secret list` (and thus can end up printed in a chat transcript, terminal history, screen share,
etc., depending on however that listing gets surfaced). This is a real, easy-to-make mistake,
not just a hypothetical — caught in a real session via routine `wrangler secret list` output.

**If this happens, and the leaked value is a live credential shared with another system** (e.g.
the same secret configured in a third-party webhook's auth header), treat it as genuinely
compromised: delete the bad Cloudflare secret entry, **rotate the value everywhere it's used**
(not just delete-and-recreate the Cloudflare side with the same now-exposed value), and only
then set the new value correctly (`wrangler secret put NAME`, value at the prompt). When
relaying a freshly rotated value to a human who needs to paste it into multiple UIs (e.g. both
the third-party service's config and the origin's own credential store), write it to a local
file instead of printing it in any tool output, have them view/copy it themselves
(`cat <file>` in their own terminal), and delete the file once every place that needed it has
been updated — don't print it "just this once" even under time pressure.

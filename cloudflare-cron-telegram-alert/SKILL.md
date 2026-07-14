---
name: cloudflare-cron-telegram-alert
description: This skill should be used when scaffolding a Cloudflare Worker that runs on a cron trigger, checks something external (a URL, an API, a heartbeat), and sends a Telegram alert only on failure — e.g. an uptime monitor, a health check, a dead-man's-switch. Trigger phrases include "cron trigger uptime monitor", "Telegram alert Worker", "cloudflare cron health check", "scheduled Worker Telegram", "uptime monitor Cloudflare Worker", "dead man's switch worker".
---

# Cloudflare Cron + Telegram Alert Worker

A minimal, reusable shape for "check something on a schedule, alert only when it's broken" —
built out fully for a tailnet uptime monitor; the same shape fits any periodic external check.

## Project shape

```
wrangler.jsonc      # cron trigger, no public route (see below)
src/index.ts        # scheduled() handler + fetch() stub
package.json
tsconfig.json
.gitignore          # node_modules/, .wrangler/, .dev.vars, worker-configuration.d.ts
```

`wrangler.jsonc` essentials:
```jsonc
{
  "name": "<worker-name>",
  "main": "src/index.ts",
  "compatibility_date": "<recent date>",
  "observability": { "enabled": true },
  "workers_dev": false,      // no public HTTP route needed — cron-only
  "preview_urls": false,
  "triggers": { "crons": ["*/5 * * * *"] }
}
```

**Disable `workers_dev`/`preview_urls` explicitly.** A cron-only Worker gets a public
`*.workers.dev` route by default on first deploy unless these are set — unnecessary attack
surface for something that never needs inbound HTTP.

## Handler pattern

```typescript
export interface Env {
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  TARGET_URL: string;
}

export default {
  async scheduled(_event, env, ctx): Promise<void> {
    ctx.waitUntil(checkTarget(env));
  },
  async fetch(): Promise<Response> {
    return new Response("cron-only Worker; use wrangler dev --test-scheduled to test");
  },
} satisfies ExportedHandler<Env>;

async function checkTarget(env: Env): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const res = await fetch(env.TARGET_URL, { signal: controller.signal });
    if (!res.ok) await sendTelegramAlert(env, `Check FAILED: ${res.status} ${res.statusText}`);
  } catch (err) {
    await sendTelegramAlert(env, `Check FAILED: ${err instanceof Error ? err.message : err}`);
  } finally {
    clearTimeout(timeout);
  }
}

async function sendTelegramAlert(env: Env, text: string): Promise<void> {
  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: env.TELEGRAM_CHAT_ID, text }),
  });
  if (!res.ok) console.error(`Telegram alert delivery failed: ${res.status} ${await res.text()}`);
}
```

**Alert only on failure — never on success.** No "still up" ping every cron cycle. This matches
the minimal-noise-notification standard already used for Grafana alerting in this homelab; a
Worker that pings Telegram every 5 minutes even when healthy trains the recipient to ignore the
channel.

## Secrets, not vars

All three values (bot token, chat ID, target URL) go in as `wrangler secret put <NAME>` —
interactive prompt or piped via `printf '%s' "$VALUE" | wrangler secret put NAME`, never as a
CLI argument or `vars` in the committed config, even for values that aren't strictly sensitive
(the target URL, for instance) — keeps the pattern uniform and avoids the actual secrets
(bot token) accidentally sitting next to a hardcoded non-secret in the same config block.

## Testing before deploy

```bash
# .dev.vars (gitignored) with the same keys as a fake/test target
npx wrangler dev --test-scheduled --port 8788 &
curl http://localhost:8788/__scheduled
```

Test **both** paths before deploying: point `TARGET_URL` at something healthy (expect silence,
no Telegram call) and at something unreachable (expect a logged Telegram delivery attempt, even
if the bot token is a placeholder and the call itself 404s — that still proves the failure branch
fires correctly).

## Verifying in production

`wrangler tail` shows real cron invocations (`"*/5 * * * *" @ <time> - Ok`), but macOS has no
`timeout` binary by default — don't chain `timeout N wrangler tail`; run it via `nohup ... &`
and kill it manually, or use the harness's own backgrounding (`run_in_background: true` on the
Bash tool) instead of trying to bound it client-side.

## The big gotcha: what can this Worker actually reach?

If the check target lives on a private network (a Tailscale Serve URL, an internal VPN address,
a LAN-only host), **a Cloudflare Worker cannot reach it** — Workers run on Cloudflare's public
edge, not inside any private network. A Tailscale Serve hostname resolves via real public DNS
(needed for the HTTPS cert) to the node's private tailnet IP (CGNAT `100.64.0.0/10`), which is
only routable from inside that tailnet — the Worker's `fetch()` will fail every single cron
cycle, indistinguishable from "the service is actually down." Before wiring the target URL,
confirm the check target is genuinely reachable from the public internet — a Tailscale Funnel
endpoint (not Serve), a real public IP, or an intentionally-exposed health path. See the
`proxmox-terraform-provisioning` skill / this project's Tailscale gotchas for the pattern of
narrowing a Funnel'd endpoint to a single secret-gated health path rather than exposing a whole
app just to make it checkable from outside.

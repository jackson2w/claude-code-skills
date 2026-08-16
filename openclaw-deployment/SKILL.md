---
name: openclaw-deployment
description: This skill should be used when deploying or debugging a self-hosted OpenClaw (formerly Clawdbot/Moltbot) agent gateway — a Node.js personal-assistant service bridging Telegram/WhatsApp/Discord to an LLM with tool/skill access. Covers install, secure baseline config (loopback bind, token auth, exec approval gating), the two non-obvious config traps that silently break things (model selection vs. API key, exec security vs. ask), Telegram channel lockdown, and building trustworthy custom skills instead of pulling from the unvetted ClawHub marketplace. Trigger phrases include "openclaw config", "openclaw gateway", "tools.exec.security", "openclaw model not found", "ProviderAuthError No API key found for provider openai", "exec denied security=deny", "openclaw dashboard", "openclaw pairing", "ClawHub skill", "openclaw skills install local".
---

# OpenClaw deployment

Built and verified end-to-end 2026-08-16 deploying a personal instance on a Vultr VPS
(`dfw`), wired to Telegram, Anthropic, GitHub, and Cloudflare. Every gotcha below was hit for
real — found by reading actual error logs and `openclaw config schema`, not by trusting docs
pages (several official doc pages returned "not found in this excerpt" for exactly the config
keys that mattered most; the installed CLI's own `config schema` output is the real source of
truth).

## Install

```bash
# Node.js via NodeSource (nodistro repo works fine on Debian 13/trixie, see
# proxmox-node-systemd-service skill for the full apt-repo setup sequence)
npm install -g openclaw@latest
openclaw --version
```

Run as a dedicated non-root, non-login system user (`adduser --disabled-password
--disabled-login openclaw; passwd -l openclaw`), managed via a systemd unit with `User=openclaw`,
`ProtectSystem=strict`, `PrivateTmp=true`, `ReadWritePaths=/home/openclaw/.openclaw`.

## Gotcha 1 — setting the API key does NOT select which model gets used

Configuring `models.providers.anthropic.apiKey` is necessary but not sufficient. Without also
setting a default model, the gateway silently defaults to `openai/gpt-5.5` — and if no OpenAI key
is configured (because you're using Anthropic), every request fails:

```
ProviderAuthError: No API key found for provider "openai". Auth store: ...
model fallback decision: decision=candidate_failed requested=openai/gpt-5.5 ... reason=auth
```

This looks like an Anthropic auth problem. It isn't — the Anthropic key is fine, the *model
selection* just defaulted somewhere else entirely. Fix:

```json5
{ agents: { defaults: { model: "anthropic/claude-sonnet-5" } } }
```

Don't guess the model string — OpenClaw maintains its own alias registry that doesn't
necessarily match Anthropic's raw API model IDs, and it changes over time. Get the current valid
list straight from the installed CLI:

```bash
openclaw models list
```

## Gotcha 2 — `tools.exec.security: "deny"` is a HARD BLOCK, not an approval gate

The two exec-control fields look like they compose, but they don't the way you'd expect:

- `tools.exec.security`: `deny` | `allowlist` | `full` — **eligibility gate**. `deny` refuses
  every exec call outright, unconditionally, before `ask` is ever consulted.
- `tools.exec.ask`: `off` | `on-miss` | `always` — **approval-prompt control**. Only matters for
  calls that already passed the `security` gate.

If you want "the agent can run anything, but must ask permission every time" (a common and
sensible posture for a personal assistant with real infra access), the correct pairing is:

```json5
{ tools: { exec: { security: "full", ask: "always" } } }
```

**Not** `security: "deny"` — that sounds like the safer/stricter choice and is the literal value
shown in some published "secure baseline" examples, but it silently refuses everything with no
prompt ever sent. Symptom in the logs when this is misconfigured:

```
[tools] exec failed: exec denied: host=gateway security=deny raw_params={...}
[tools] exec failed: exec denied: host=sandbox security=deny raw_params={...}
```

Both `host=gateway` and `host=sandbox` get tried and both refuse — no approval request is ever
generated. Confirm the fix actually worked by watching for the real approval flow in the logs
after a live test:

```
[ws] ⇄ res ✓ exec.approval.request 68ms ...
[ws] ⇄ res ✓ exec.approval.waitDecision 8946ms ...
```

The `waitDecision` timing (matches how long the human actually took to respond) is the tell that
it's genuinely gating on a live decision, not rubber-stamping.

When in doubt about any enum's valid values, don't trust doc pages piecemeal — pull the schema
directly from the installed binary:

```bash
openclaw config schema > /tmp/openclaw-schema.json
python3 -c "
import json
s = json.load(open('/tmp/openclaw-schema.json'))
def find(o, path=''):
    if isinstance(o, dict):
        if 'enum' in o: print(path, o['enum'])
        for k,v in o.items(): find(v, path+'/'+k)
    elif isinstance(o, list):
        for v in o: find(v, path)
find(s)
"
```

## Exec sandboxing interacts badly with a host-level uid firewall

`agents.defaults.sandbox` (Docker/Podman-based exec isolation) puts sandboxed commands in their
own network namespace. If you've also built a host-level outbound firewall scoped by uid (e.g.
nftables `meta skuid <id>` rules) to restrict what the service account can reach, **that firewall
will not apply to sandboxed exec calls** — Docker's networking bypasses it entirely unless you
build a second, separate firewall for the Docker network (e.g. `DOCKER-USER` iptables chain
rules). This is a general Docker-vs-`ufw`/host-firewall gotcha, not OpenClaw-specific, but it's
easy to only discover once you've built both pieces separately and assumed they compose.

Given `security: "full"` + `ask: "always"` already means nothing executes without a live human
decision, treat Docker sandboxing as an *additional* defense-in-depth layer to add deliberately
later (with its own matching network firewall), not something to enable casually alongside a
host-level firewall and assume both apply.

## Uid-scoped outbound firewall (composes correctly with `ufw`)

To restrict what the service account can reach outbound (e.g. only the LLM/messaging/deploy
APIs it actually needs, plus one explicit SSH carve-out to a specific internal host) without
touching `ufw`'s own tables: add a **separate** nftables table at a **later** priority than
`ufw`'s default (`filter + 10` composes correctly after `ufw`'s `priority 0` — nftables
processes all base chains at a given hook across all tables, in priority order; `ufw`'s ACCEPT
at priority 0 doesn't terminate the hook, so your later-priority DROP still gets evaluated):

```
table inet openclaw_egress {
  chain output {
    type filter hook output priority 10; policy accept;
    oifname "lo" accept
    meta skuid 1002 tcp dport 443 accept
    meta skuid 1002 udp dport 53 accept
    meta skuid 1002 tcp dport 53 accept
    meta skuid 1002 tcp dport 22 ip daddr <trusted-host-ip> accept
    meta skuid 1002 counter drop
  }
}
```

**The `oifname "lo" accept` line is not optional.** OpenClaw's own gateway process connects to
*itself* over loopback (`127.0.0.1:<gateway-port>`) for its internal exec-approval handler — this
is not exposed traffic in any meaningful sense (it never leaves the host), but a uid-scoped
egress rule with no loopback exemption drops it exactly like any other unlisted destination.
Symptom: exec calls silently hang forever with no approval prompt ever reaching Telegram, no
error surfaced to the user, and only an occasional `[telegram] failed to start native approval
handler: Error: connect ETIMEDOUT 127.0.0.1:<port>` in the gateway's own logs as a clue — easy to
miss since the gateway otherwise looks completely healthy (`systemctl status` active, Telegram
polling running, model API calls succeeding). Confirm via `nft list table inet openclaw_egress`
— a nonzero packet counter on the final `drop` rule while loopback connections are failing is
the tell. **After building this firewall, always re-run a live end-to-end exec-approval test
(not just the external allow/deny checks) — the loopback break only shows up when something
actually tries to invoke exec, not from checking connectivity to external hosts.**

Never `nft flush ruleset` to apply this (wipes `ufw`'s and `tailscaled`'s own tables too — see
the homelab's general Tailscale/nftables gotcha). Use `nft delete table inet openclaw_egress
2>/dev/null; nft -f <file>` — scoped to just this one table, safe to re-run. Persist via a
systemd oneshot unit (`ExecStart=` that same delete-then-load line, `RemainAfterExit=yes`), not
`nftables.service`/`/etc/nftables.conf` if `ufw` isn't already using that mechanism on the host
(check `systemctl is-active nftables` first — if `ufw` is managing its own tables independently,
adding your rules into the same lifecycle is unnecessary and can cause confusion about which
mechanism owns what).

Verify both the allow and deny cases explicitly, as the target uid — a passing curl to an
allowed host doesn't prove the deny side works:

```bash
sudo -u openclaw curl -s -m 5 -o /dev/null -w '%{http_code}\n' https://api.anthropic.com/
sudo -u openclaw timeout 5 bash -c 'echo > /dev/tcp/<some-other-internal-host>/22' \
  2>&1 && echo "BAD: connected" || echo "good: refused"
```

## Telegram channel lockdown

Numeric user ID only — Telegram usernames/phone numbers are not accepted in `allowFrom`. Get
your own ID via `/whoami@<bot_username>` in a DM, or from the pairing request record.

Initial setup uses `dmPolicy: "pairing"` (generates a one-time code on first DM), approved via:

```bash
openclaw pairing list telegram
openclaw pairing approve telegram <CODE>
```

The first approval auto-bootstraps `commands.ownerAllowFrom` if empty. **This does not fully
lock the channel down by itself** — anyone can still trigger a new pairing *request* (even if
they can't get approved) while `dmPolicy` stays `"pairing"`. For a single-owner personal
instance, switch to a hard allowlist afterward so no one else can even initiate pairing:

```json5
{
  channels: { telegram: { dmPolicy: "allowlist", allowFrom: ["<your-numeric-id>"] } },
  commands: { ownerAllowFrom: ["telegram:<your-numeric-id>"] }
}
```

## Skills: prefer first-party bundled or local-authored over ClawHub

`openclaw skills search <name>` queries ClawHub, an open, unvetted community marketplace —
results routinely include several near-duplicate submissions from different authors under the
same apparent name, and outright spam/SEO-farming content mixed in. Before installing anything
from there, check whether a **first-party bundled** skill already covers it — these ship with
OpenClaw itself (`Source: openclaw-bundled` in `openclaw skills info <name>`) and just need a
binary requirement satisfied to go from `△ needs setup` to `✓ ready`:

```bash
openclaw skills list                  # shows bundled skills gated on missing binaries
openclaw skills info <name>           # confirms Source: openclaw-bundled vs. clawhub/other
```

Example: the bundled `github` skill needs only the official `gh` CLI installed — no ClawHub
install required at all, and it's first-party-trusted rather than arbitrary community code.

For anything with no bundled equivalent (e.g. Cloudflare, as of this writing), author a small
local `SKILL.md` yourself instead of pulling an unreviewed ClawHub entry — same frontmatter
shape as bundled skills, installed via:

```bash
openclaw skills install <local-dir> --as <slug>
```

This keeps every piece of skill *code* either first-party or self-authored, with only
credentials (scoped API tokens) as the actual trust boundary being extended to third parties.

## Dashboard / Control UI

`openclaw dashboard` opens a web Control UI — but if the gateway is `bind: "loopback"` (the
right choice per OpenClaw's own security docs for anything with real infra access), it's only
reachable from the box itself at `http://127.0.0.1:<port>/`. From a workstation, either SSH
port-forward (`ssh -L <port>:127.0.0.1:<port> user@host`, then open the URL locally) or expose it
deliberately via the same reverse-proxy pattern used for everything else (Tailscale Serve on its
own port, not the loopback bind). Get the real bound port and dashboard URL from:

```bash
openclaw gateway status --deep
```

This same command is the right first diagnostic for "the CLI can't connect to my running
gateway" — it separates "gateway process isn't running" from "gateway is running but the CLI's
own auth/probe handshake is failing" (the latter showed up as a `Connectivity probe: failed /
timeout` even with the gateway confirmed `running` and correctly bound — a CLI-context auth
issue, not a service-health issue; don't treat it as proof the gateway itself is unhealthy).

Logging into the dashboard from a browser takes two more steps beyond just the URL:

1. **`openclaw config get gateway.auth.token` prints `__OPENCLAW_REDACTED__`, not the real
   value** — the CLI deliberately masks secrets in its own terminal output. Read the raw config
   file instead: `python3 -c "import json; print(json.load(open('~/.openclaw/openclaw.json'))
   ['gateway']['auth']['token'])"` (expand `~` or use the real path).
2. **The Control UI needs its own device-pairing approval**, separate from any channel (Telegram
   etc.) pairing already done — first connection attempt shows "Device pairing required" with a
   request ID. Approve it the same way as a channel pairing, just a different command:
   `openclaw devices list` / `openclaw devices approve <request-id>`.

## Secrets: two valid patterns, pick per-field based on what's documented

- `SecretRef` sourced from env (for values wired through the systemd unit's `EnvironmentFile=`):
  `{ "source": "env", "provider": "default", "id": "ANTHROPIC_API_KEY" }`
- Plaintext directly in `openclaw.json` (for values with no natural env-var home, like the
  gateway's own auth token) — OpenClaw's own docs explicitly say to protect this via file
  permissions (`chmod 600 ~/.openclaw/openclaw.json`, `chmod 700 ~/.openclaw/`), confirming this
  is an intended, not accidental, pattern.

Generate any value that needs to land in either place server-side, in one script, so it never
transits through your own shell history or an assistant's chat transcript.

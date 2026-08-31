---
name: hermes-agent-deployment
description: This skill should be used when deploying or debugging a self-hosted Hermes Agent (Nous Research's self-hosted personal-assistant gateway bridging Telegram/WhatsApp/Slack/Discord to an LLM with tool/skill/cron access — Will calls his instance "Chuka") — including install via the `hermes` CLI, the `hermes-gateway.service` systemd unit, native `hermes cron` scheduled jobs, the `hermes skills` system (SKILL.md drop-in files distinct from Claude Code's own skills), Debian 13 install gotchas (python3.13-venv, broken IPv6/gai.conf), fleet-readonly SSH access design, or UID-scoped egress firewalling. For credential protection via Agent Vault specifically, see the separate `agent-vault-credential-broker` skill — this skill covers Hermes's own deployment, not the broker. Trigger phrases include "hermes agent", "hermes gateway", "hermes cli", "hermes cron create", "hermes skills list", "hermes-gateway.service", "hermes mcp install", "ensurepip is not available", "HERMES_HOME", "hermes gateway install --system", "chuka", "hermes_cli.main gateway run", "LunaRoute glm-5.3-flash", "hermes fleet access", "hermes-remote", "hermes_egress table".
---

# Hermes Agent deployment

Built and verified end-to-end 2026-08-31 deploying a personal instance on a Vultr VPS
(`hermes-agent`, Dallas, Debian 13), wired to Telegram, LunaRoute (custom LLM provider), and
Groq (voice transcription) — Will's nickname for the running instance is "Chuka" (a personal
name, not an infra rename; every host/user/vault stays `hermes-*`). Every gotcha below was hit
for real building it and its follow-on capabilities, not assumed from docs. Deliberately kept
separate from the `homelab-ansible`-managed fleet (Will's call) but, per his standing
Ansible-first instruction for this project, fully Ansible-managed from day one via its own
`hermes-ansible` repo run **locally on the box** (`ansible_connection=local`), mirroring how
`dfw-ansible` runs locally for OpenClaw rather than being pushed from `ansible-ctrl`.

## Install

```bash
npm install -g @nousresearch/hermes-agent   # exact package name — verify against current docs,
                                             # this is a fast-moving research-preview tool
hermes --version
```

Run as a dedicated non-root `hermes` system user — Hermes's own installer refuses `--system`
install as root without an override, since running a Telegram-driven exec-capable process as
root indefinitely is a real risk, same reasoning as OpenClaw's `openclaw` user.

Gateway service install is a CLI subcommand, not a hand-written unit file:

```bash
hermes gateway install --system --run-as-user hermes --start-now --start-on-login
```

Confirmed idempotent as-is — a second invocation prints "Service already installed ... Use
--force to reinstall" and just ensures the service is running; it does **not** silently no-op
forever, so **don't** add a `creates:` guard in Ansible around this command (that would
permanently block a deliberate future reinstall, e.g. after a CLI upgrade changes the generated
unit template — same "creates: guard blocks upgrade" failure shape documented in the
`proxmox-node-systemd-service` skill for n8n). Use an idempotency check on the command's own
stdout instead (`changed_when: "'already installed' not in result.stdout"`), and a separate
`-e hermes_gateway_force_reinstall=true`-gated `--force` path for deliberate reinstalls.

The resulting unit (`hermes-gateway.service`) has **no** `ProtectSystem=`/`ReadWritePaths=`
hardening by default — plain `Type=simple`, `User=hermes`, `WorkingDirectory=/home/hermes/.hermes`,
`ExecStart=<venv>/bin/python -m hermes_cli.main gateway run`. This matters if you ever wrap it
with `agent-vault run --` or add hardening later — no pre-existing `ReadWritePaths=` mount-
namespace gotcha to worry about here (unlike OpenClaw's already-hardened unit).

## Two real Debian 13 install-time gotchas, baked into Ansible so a rebuild doesn't rediscover them

1. **`python3.13-venv` isn't preinstalled.** `hermes mcp install <name>` bootstraps each MCP
   server into its own venv via the *system* `python3 -m venv`, not Hermes's own bundled
   interpreter — fails with `ensurepip is not available` until `apt install python3.13-venv`
   (or whatever minor version matches `python3 --version` — don't hardcode `3.13`, derive it).
2. **Broken outbound IPv6 + DNS still returning AAAA records.** This VPS class has no real IPv6
   route (`curl -6 https://api.telegram.org` hangs/fails) but some hosts still resolve an
   IPv6-only AAAA record, so glibc's `getaddrinfo()` prefers a dead candidate by default. Fix:
   uncomment `precedence ::ffff:0:0/96 100` in `/etc/gai.conf` (deprioritizes IPv6 without
   disabling it — general OS hygiene, not disruptive). **Note**: this was NOT the actual root
   cause of a real Telegram-connection hang hit the same day — Hermes's own Telegram adapter
   already has a hostname-preserving IPv4-literal fallback transport built in for exactly this
   "blackholed IPv6 AAAA" scenario. Keep the `gai.conf` fix anyway as correct-regardless-of-cause
   OS-level hygiene for any *other* process on the box that lacks Hermes's own workaround.

## Config and secrets

`~/.hermes/config.yaml` — model provider config (`providers.<name>.base_url`/`key_env`/
`api_mode`), voice/STT provider (`groq: model: whisper-large-v3-turbo`), memory settings. This
project's instance uses a **custom** provider, `custom:lunaroute` (LunaRoute — an OpenAI-
compatible `chat_completions`-mode gateway, `base_url: https://gw.lunaroute.com/v1`), not a
first-party Anthropic/OpenAI provider — check `config.yaml` directly for the real auth header
shape before assuming a custom provider is plain bearer auth (it happened to be, here, but that's
not guaranteed for every custom provider).

`~/.hermes/.env` holds credential values Hermes reads at its own application layer (via
python-dotenv or similar) — **these do not appear in `/proc/<pid>/environ`** even after the
gateway is running, since Hermes loads `.env` itself rather than relying on systemd's
`EnvironmentFile=` for it. Don't use a `/proc/<pid>/environ` check to verify `.env` changes took
effect — check the file's own content (structurally, e.g. `cut -d= -f1` for field names, never
`cat`/`grep` a full line — see the credential-rotation-protocol skill) and confirm via a real
functional test instead. See the separate `agent-vault-credential-broker` skill for how this
project migrated `.env`'s three real values (LunaRoute/Telegram/Groq) to placeholders backed by
Agent Vault — that migration uses a genuinely different systemd wiring pattern than OpenClaw's
(a plain `HTTPS_PROXY`/CA-trust `EnvironmentFile=` via a `.service.d/override.conf` drop-in, not
an `ExecStart` wrapper), confirmed via Agent Vault's own `hermes-on-vps.mdx` guide, not guessed
from OpenClaw's pattern.

**Real, generalizable gap found 2026-08-31**: if a credential is ever set up by pasting the real
value into a chat message *with Hermes itself* (e.g. asking Chuka to write it into `.env` for
you), that value persists in Hermes's own `state.db`/session history indefinitely, surviving
both a later `.env` scrub and a provider-side key rotation. Always set new credentials directly
via the Agent Vault CLI (or hand-edit `.env` yourself) — never relay a real secret value through
a message to the agent.

## Native scheduling: `hermes cron`

Hermes ships a full first-party cron system — durable (tracked in `~/.hermes/cron/*.db` with
real run history, survives gateway restarts), **not** analogous to Claude Code's session-scoped
`CronCreate` tool. Key subcommands:

```bash
hermes cron list                                    # see existing jobs
hermes cron create '<schedule>' '<prompt>' \
  --name <name> --deliver telegram --skill <skill-name>
hermes cron run <name>                               # fire on the next tick, for testing
hermes cron runs <job-id>                            # durable execution history
```

Schedule accepts cron syntax (`0 12 * * 0`) — **the box's own system timezone applies** (UTC by
default on a fresh Vultr Debian image; check `timedatectl` before picking a schedule, don't
assume it matches Will's local time). `--deliver telegram` sends the job's final response
straight to the paired chat; the prompt is automatically told it's running as an unattended cron
job and to respond with exactly `[SILENT]` (nothing else) to suppress delivery when there's
nothing to report — a real, working convention, not something to reinvent.

No dedup/idempotency built into `cron create` itself — an Ansible task wrapping it needs its own
`hermes cron list | grep <name>` guard before creating, or a re-run duplicates the job.

Verify a new job for real, don't trust "created successfully" alone: `hermes cron run <name>`
then check `~/.hermes/cron/output/<job-id>/*.md` for the actual rendered prompt + response —
this project caught a version-drift discrepancy (an LLM-reported n8n version newer than the last
confirmed-live one) this way, worth a quick sanity skim even on a "successful" test run.

## `hermes skills` — a separate skills system from Claude Code's own

Hermes has its own bundled skills feature, unrelated to `~/.claude/skills/` — a plain file drop
at `~/.hermes/skills/<category>/<name>/SKILL.md` is sufficient for registration, no install
step. Verify via `hermes skills list` (shows name/category/source/trust/status columns). Used in
this project to give Hermes durable operational knowledge about its own SSH-based fleet access
(which user, which host, which dispatch-script subcommands) after a live session tried 12 wrong
usernames and misread an intentional egress-firewall timeout as a bug — the fix was documentation
Hermes could actually read, not a config change.

## Fleet-readonly/changes SSH access pattern

This project gave Hermes SSH-based visibility (and later, a curated non-destructive changes
capability) into the wider homelab fleet, structured identically to OpenClaw's own equivalent on
`dfw` but as a **fully independent identity** — separate SSH keypair, separate system user
(`hermes-remote` on `ansible-ctrl`, `hermes-dfw-remote` on `dfw`), separate dispatch scripts and
sudoers grants, never shared or generalized with OpenClaw's. "The dispatch script is the security
boundary, not the sudoers grant" — curated, array-based, no-shell-interpolation scripts; sudoers
scoped to exactly one script path each; destructive operations categorically excluded rather than
prompt-gated. The **changes** dispatch script (as opposed to the readonly one) is deliberately
never added to Hermes's own `command_allowlist`, so every invocation still triggers a live
Telegram approval — the same split OpenClaw uses.

## UID-scoped egress firewall (`hermes_egress` nftables table)

Same defense-in-depth pattern as `dfw`'s `openclaw_egress` table (see
`reference_openclaw_egress_firewall`) — once Hermes holds any real SSH key or credential worth
protecting, a `meta skuid <hermes-uid>`-scoped nftables table allowlists only: outbound 443/53 to
any destination (the model provider, Telegram, GitHub, apt), and SSH (22)/Agent Vault's proxy
ports (14321/14322) to specific Tailscale IPs only. Everything else hits a counted `drop`. Look
up the UID at deploy time via `getent`, never hardcode it — this project's `hermes` user is UID
999, no reason to assume it matches another host's service account. Diagnostic signature for a
missing rule: a **TCP timeout** (not "connection refused") from this specific UID, easily
mistaken for a Tailscale ACL or destination-side problem.

## Telegram identity

`getMe` against the live bot token returns `{"id": 8810663021, "username": "DFWHermesBot",
"first_name": "Chuka Hermes", ...}` — useful as a sanity check after any credential change
(bot-token mixups have happened twice on this project's other Telegram bots during unrelated
rotations; confirm the numeric `id` matches, not just that *some* bot responds).

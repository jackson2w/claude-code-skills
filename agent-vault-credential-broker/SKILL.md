---
name: agent-vault-credential-broker
description: This skill should be used when deploying or debugging Infisical's Agent Vault (a self-hosted, research-preview credential broker that intercepts an agent's outbound HTTPS calls via a local MITM proxy and injects real API keys so the agent process never holds them) — including provisioning a new instance, wiring it in front of an existing agent (OpenClaw, Hermes, a coding agent), the `agent-vault` CLI (vault/service/agent/run subcommands), or debugging a broken cutover. Trigger phrases include "agent vault", "credential broker", "get.agent-vault.dev", "agent-vault run", "AGENT_VAULT_TOKEN", "AGENT_VAULT_ADDR", "AGENT_VAULT_VAULT", "mitm-ca.pem", "agent-vault server", "unmatched_host_policy", "openclaw-on-vps.mdx", "hermes-on-vps.mdx", "placeholder api key vault", "__anthropic_api_key__", "Failed to set up mount namespacing", "agent process never holds credential", "MITM proxy inject api key", "vault service add catalog", "netguard blocked by network policy", "AGENT_VAULT_NETWORK_ALLOWLIST", "AGENT_VAULT_ALLOW_PRIVATE_RANGES", "agent vault 502 internal host", "agent vault tailnet private ip blocked".
---

# Agent Vault (Infisical) — credential broker for agent processes

Built and verified end-to-end 2026-08-31 deploying a new instance and cutting an existing
OpenClaw gateway over to it. It's a **research preview** — re-check
`https://github.com/Infisical/agent-vault` and its `docs/` folder before trusting any exact
command here to still be current.

## What it actually protects against (and what it doesn't)

Agent Vault intercepts an agent's **own outbound HTTPS API calls** via a local MITM proxy
(`HTTPS_PROXY` + a trusted CA) and injects the real credential at the network layer — the agent
process's own environment only ever holds a placeholder. This is the right tool when the agent
*itself* holds a raw provider key and makes its own outbound calls with it (an OpenClaw/Hermes-
style gateway, a service account). It does **not** help with a human-driven interactive session
(e.g. Claude Code on a laptop) exposing a secret via an SSH command's output or shell history —
that's a command-construction/history-hygiene problem, not a network-credential-injection one.
Don't scope a pilot at "stop this specific SSH leak" without checking the mechanism actually
covers it first.

## Deployment placement

**Must run on a separate machine from the agent(s) it protects** — the vendor's own docs are
explicit about this; co-locating defeats the isolation (a compromised agent session could reach
the local vault/master password). For a Proxmox-based fleet with a VMID convention, this is
exactly what a "security-isolated/agentic" VMID range is for.

Install via `curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL
https://get.agent-vault.dev | sh` (binary + systemd-style layout) or the `infisical/agent-vault`
Docker image (ports `14321` mgmt UI, `14322` MITM proxy). Bind both ports to the instance's
Tailscale IP specifically, never `0.0.0.0` — verify with `ss -tlnp`, not just "I set `--host`".
Master password (`AGENT_VAULT_MASTER_PASSWORD`) has no built-in backup guidance from the tool
itself; treat it the same as any other durable secret — generate strong, back up off-host
before relying on the instance.

**No native TLS on the mgmt/API port** — confirmed via `agent-vault server --help` and the
vendor's own env-var docs: there's no TLS flag or config option at all, the server is plain HTTP
by design (default `--host` is even `127.0.0.1`), and the docs assume you'll front it with a
reverse proxy or platform-native TLS (Fly.io is their own example) if you want HTTPS. For a
Tailscale-only deployment, front the mgmt port (14321, not the MITM proxy port 14322 — see
below) with Tailscale Serve, matching this homelab's standard access pattern:
`tailscale serve --bg --https=443 http://<the-instance's-own-tailscale-IP>:14321` — **use the
instance's own Tailscale IP as the proxy target, not `localhost`**, since the server is bound to
that IP specifically, not loopback (`localhost:14321` gets a `502` from Serve, not a connection).
Purely additive — the raw port stays reachable unless separately blocked (see below). Then
update every consumer's `AGENT_VAULT_ADDR` (`gateway.env`, `openclaw-agentvault.env`, etc.) to
the new `https://` hostname and restart each gateway — the MITM proxy env vars
(`HTTPS_PROXY`/`HTTP_PROXY`) stay pointed at the raw IP:14322, unaffected.

**To actually enforce HTTPS-only (not just make it available)**, block the raw port at the host
firewall rather than relying on `--host` alone — `agent-vault server` has a single `--host` flag
covering *both* the mgmt port and the MITM proxy, so rebinding just the mgmt port to loopback
isn't possible without also breaking the MITM proxy for every consumer that reaches it directly
via the Tailscale IP. The fix: add an nftables rule dropping the mgmt port specifically when it
arrives from a real tailnet peer, while leaving Serve's own backend connection untouched —
`iifname "tailscale0" tcp dport 14321 drop` in the host's own `inet filter` input chain (don't
touch tailscale's own `iptables-nft`-managed tables, add to a separate/existing plain table
instead). This works because a same-host connection to the box's *own* Tailscale IP routes via
`lo`, not `tailscale0` (confirmed via `ip route get <own-tailscale-ip>` showing `dev lo`), so
Serve's own reverse-proxy connection to the backend never matches the drop rule while a genuine
external peer's direct connection does. Verify both directions: direct `http://` to the raw IP
times out/fails, `https://` via the Serve hostname still returns 200, and the MITM proxy port is
unaffected. If persisting this in `/etc/nftables.conf` (Debian's base nftables.service loads it
at boot), remember the file always starts with `flush ruleset` — editing it live is safe (takes
effect next boot only, when boot ordering means nftables.service runs before tailscaled installs
its own rules), but never `systemctl restart nftables` while tailscaled already has live rules
programmed — that flushes them too (see the Tailscale-pihole-dns-routing skill's nftables-reload
gotcha for the general case).

If the LXC/VM is unprivileged and needs Tailscale, the standard TUN-passthrough gotcha applies
(`lxc.cgroup2.devices.allow`/`lxc.mount.entry` + full stop/start, not a service restart) — not
specific to Agent Vault, covered generically elsewhere in this environment's Proxmox skills.

## Rotating `AGENT_VAULT_MASTER_PASSWORD`

Confirmed working end-to-end 2026-09-02. The master password is a KDF input (Argon2id) for a KEK
that wraps the DEK, which uniformly encrypts every stored credential — per the vendor's own
security docs, rotating it via the proper command is "a single database update with zero
credential re-encryption." It is **not** the same credential as the web UI/CLI owner-account
login (`agent-vault auth register`/`auth login`, a normal human email+password) — the two are
structurally independent; rotating one has zero effect on the other.

**Procedure** (single-instance SQLite, this project's deployment shape — no `DATABASE_URL` set):
1. `agent-vault master-password change` **refuses to run while the server is active** ("server is
   running (PID ...) -- stop it first"). Stop it via the process manager actually supervising it
   (`systemctl stop agent-vault.service` here), not `agent-vault server stop` directly, to avoid
   racing systemd's own restart handling.
2. Run `agent-vault master-password change` — interactive prompts for current password, then new
   (twice, to confirm). `--force` is only for PostgreSQL multi-instance setups with all instances
   stopped; not needed here.
3. Update the systemd `EnvironmentFile` (`/root/.config/agent-vault.env` here) so
   `AGENT_VAULT_MASTER_PASSWORD=` matches **exactly** what was just set at the prompt.
4. `systemctl start agent-vault.service`, then `systemctl status` — confirm `active (running)`,
   not `activating (auto-restart)`.

**Real gotcha hit doing this**: after rotating, the service crash-looped (`systemctl status`
showed `activating (auto-restart)`, exit code 1; `journalctl -u agent-vault.service` showed a
plain `wrong password` error). Root cause was a copy/typo mismatch between the password actually
set at the interactive prompt and what ended up written into the env file — they're typed/pasted
independently, so nothing catches a mismatch until the next start attempt. **Minimize this
surface**: generate the new password once, copy it via clipboard into both the CLI prompt and the
env file rather than re-typing/re-pasting separately, and don't consider the rotation done until
`systemctl status` shows a clean `active (running)` with no restart-loop.

**Verifying no data was lost, without touching any live credential value**: `agent-vault catalog
--json` is the wrong command for this — it's the static built-in *reference* list of supported
providers (Anthropic, OpenAI, GitHub, Cloudflare, etc.), not what's actually configured in your
vaults. Use `agent-vault vault list` (requires successfully decrypting the DB to run at all — its
mere success is already evidence the rotation worked) and `agent-vault vault service list --vault
<name>` for each vault, which prints service names/hosts/auth-type/header-or-token-*key-name*
metadata — never the actual credential values — confirming every configured service survived the
rotation intact.

**If you don't know the current password**: it's sitting in the systemd `EnvironmentFile` in
plaintext (`/root/.config/agent-vault.env` here) — have the human read it directly in their own
terminal (`cat` on that file, or any credential file, is exactly what
`~/.claude/hooks/block-credential-dump.sh` — see the `credential-rotation-protocol` skill — now
hard-blocks Claude Code itself from doing).

## CLI workflow

1. **Owner account**: the first person to `agent-vault auth register` (web UI or CLI) becomes
   the instance owner — a real human login, not something to create on someone else's behalf.
   Subsequent CLI use needs `agent-vault auth login --address http://<ip>:14321 --email <...>`,
   which prompts for the password interactively — never pipe/relay a password through an agent
   session for this.
2. **Vault**: `agent-vault vault create <name>` (defaults to `--credential-store builtin`,
   i.e. local SQLite — fine for a single-instance pilot; `infisical` backing store is for later).
   `agent-vault vault use <name>` sets the active context so subsequent commands don't need
   `--vault` repeated.
3. **Service**: check `agent-vault catalog --json` first — it has built-in entries for common
   providers (Anthropic, OpenAI, GitHub, Cloudflare, etc.) with the **real** header name, which
   is not always `Authorization` (Anthropic's is `x-api-key` — confirmed via the catalog JSON,
   not guessed). Add with `agent-vault vault service add --name <n> --host <host> --auth-type
   api-key --api-key-header <header> --api-key-key <CREDENTIAL_KEY>`.
4. **Credential**: `agent-vault vault credential set KEY=$(...)` — the value is a literal argv
   string, so assemble it entirely within a single-quoted remote-shell command (never build the
   value locally where it'd transit visible output); see the credential-rotation-protocol skill
   for the general discipline. Verify success by byte-length comparison against the source, not
   by printing the value — a failed extraction (e.g. `grep` permission-denied inside a
   `$(...)`) silently sets an **empty string**, and the CLI still reports "✓ Set credential"
   either way.
5. **Agent identity**: `agent-vault agent create <name> --role no-access --vault
   <vault>:proxy --token-only` — mint a separate identity per consumer, never reuse one across
   multiple agents/services (same principle as any credential scoping).
6. **Wrapping**: `agent-vault run --vault <name> -- <command>` is the documented, correct way
   to wrap either an interactive CLI (admin mode, reuses the on-disk `auth login` session,
   mints a fresh scoped token per invocation) or an unattended systemd service (agent mode:
   pre-supply `AGENT_VAULT_TOKEN`/`AGENT_VAULT_ADDR`/`AGENT_VAULT_VAULT` via
   `EnvironmentFile=`). It sets `HTTPS_PROXY`/`HTTP_PROXY`, all the CA-trust env vars
   (`SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE`,
   `GIT_SSL_CAINFO`, `DENO_CERT`), and `NODE_USE_ENV_PROXY=1` automatically — **don't hand-
   assemble these as a raw `EnvironmentFile=`**, that's how a first attempt broke unrelated
   outbound traffic (see below).

## Check for a named integration guide before hand-wiring

The repo ships `docs/guides/<tool>-on-<platform>.mdx` for common pairings (confirmed:
`openclaw-on-vps.mdx`, `hermes-on-vps.mdx`) — genuinely different config shapes per tool. Check
for one before assembling a config from the generic README/`--help` text; two guessed-wrong
attempts (a `proxy.enabled` config key that doesn't exist for a plain-env-var install; a hand-
rolled `HTTPS_PROXY` that broke non-target traffic) both would've been avoided by finding the
real guide first. Different tools want genuinely different patterns — OpenClaw's example wraps
`ExecStart` with `agent-vault run --`; Hermes' example instead writes placeholder strings
directly into its own `.env` plus a hand-assembled `EnvironmentFile=`. Don't assume one tool's
pattern transfers to another.

## systemd wrapping gotchas (wrapping an existing service's `ExecStart`)

- **`ReadWritePaths=` must already exist on disk** — systemd sets up the mount namespace before
  `ExecStart` runs; a missing path fails immediately (`Failed to set up mount namespacing: ...:
  No such file or directory`, `226/NAMESPACE`) and crash-loops on `Restart=always`.
  `agent-vault run` writes its CA cert to `~/.agent-vault/mitm-ca.pem` under the invoking user's
  home on first run — if wrapping a hardened systemd unit (`ProtectSystem=strict`), that
  directory must be **pre-created** (`mkdir -p`, correct ownership) and added to
  `ReadWritePaths=` before the restart, not assumed to appear on its own.
- **Roll back env-file and unit-file changes together, atomically** — if a cutover swaps a real
  credential for a placeholder (to prove the vault handles auth) and the unit-file change fails
  and gets rolled back, the placeholder left in the env file is a "looks completely healthy,
  silently broken" state: the service starts fine, channels connect fine, but every real
  provider call would 401 with nothing left to intercept it. Confirmed 2026-08-31 — caught
  within about a minute by remembering to check, not by any error surfacing on its own. Back up
  the real credential file before touching it (plain `cp`, not a content-modifying command —
  see below) and restore from that backup, not from memory, if a rollback is needed.
- **Verify against the live process, not just a synthetic test**: `sudo tr '\0' '\n' <
  /proc/<pid>/environ | grep '^ANTHROPIC_API_KEY='` (or equivalent) on the actual running
  service's PID is the real proof the credential swap took effect — a `curl` proving the proxy
  mechanism works in isolation doesn't prove the *specific service* picked up the change.

## If the target agent has its own egress firewall

A pre-existing UID-scoped or cgroup-scoped egress allowlist (built for defense-in-depth around
an exec-capable agent) has no way to know about a new internal service — it'll drop the new
destination by default, producing a **TCP timeout** (not "connection refused") that looks like
a Tailscale ACL or the vault's own firewall problem but isn't. Diagnostic signature: identical
network namespace/cgroup as a process that reaches the destination fine, yet still times out —
check `nft list ruleset | grep -i <service-account-name>` for a dedicated table before chasing
Tailscale. Fix is a narrowly-scoped addition (destination IP + the vault's specific ports), not
a broad port-open. See the homelab-specific `reference_openclaw_egress_firewall` memory for a
worked example.

## Confirmed live on a second cutover (Hermes, 2026-08-31) — concrete CLI gotchas

Deploying the `hermes-on-vps.mdx` pattern for real (not just reading the guide) surfaced several
exact CLI behaviors worth knowing before you hit them:

- **`agent-vault ca fetch --address` needs a full URL scheme**, not bare `host:port` — `--address
  100.117.235.3:14321` fails (`first path segment in URL cannot contain colon`); `--address
  http://100.117.235.3:14321` works. Likely applies to other subcommands' `--address` flag too.
- **`auth login`'s auto-detected "local instance" option can be wrong and must not be trusted
  blindly** — if the server is bound only to its Tailscale IP (not loopback, per the deployment-
  placement guidance above), the CLI's auto-detected `Agent Vault (127.0.0.1:14321)` option
  fails with `connection refused` even when run *on the same host* as the server. Pick "Self-
  Hosting or Dedicated Instance" and supply the real bound address explicitly instead.
- **`auth: type: custom` requires a non-empty `headers` map — it is the wrong type for a
  pure path-substitution service with no header injection at all.** `headers: {}` is rejected
  (`"headers" is required for custom auth`). Use `auth: passthrough` instead — substitutions and
  auth are independent, so a service can use either, both, or neither; `passthrough` is the
  "neither header injection nor blocking" type.
- **`agent create <name> --vault <vault>:proxy --token-only`** is the confirmed working syntax
  (default `--role` is already `no-access`; `--vault` format is `name:role`, role defaulting to
  `proxy` if omitted).
- **When the vault CLI lives on a different host than the credential's source `.env`** (true for
  any agent box that doesn't have `agent-vault` installed locally, which is normal for the
  Hermes-native pattern — no CLI install needed on the agent host at all), the non-echoing
  credential-transfer pattern spans two hosts, not one: `ssh source-host "grep '^KEY=' .env |
  cut -d= -f2-" | ssh vault-host "read -r VAL; agent-vault vault credential set --vault <v>
  KEY=\$VAL"`. Verify by piping `agent-vault vault credential get ... | wc -c` back through SSH
  and comparing byte-length against the source — never by printing the value on either end.
- **Ansible idempotency trap**: if a playbook reads a one-time-use token file (`lookup('file',
  ...)`) and then deletes it after embedding the value in a rendered template (reasonable — don't
  leave the secret duplicated on disk), a second run of that same playbook will fail outright
  (`lookup` on a missing file), not report `changed=0`. Guard both the read and the render tasks
  with a `stat` check on the token file first (`when: token_stat.stat.exists`) so a re-run
  without a fresh token cleanly skips rather than errors.

## Gap found during the Hermes cutover's plaintext-leak sweep — check this on every future cutover

**An agent's own conversation/tool-call history database can retain a credential's real value
from before it was ever migrated to the vault, even after the source `.env` is scrubbed and even
after the key is rotated at the provider.** Confirmed 2026-08-31: Hermes's `state.db` (its own
session/tool-call history) contained a fragment of the original Groq API key, verbatim, from when
it had once been set up via a chat-driven shell command (a `printf`/`grep` round-trip Hermes
itself executed at Will's request, long before this migration). This is a **structurally
different exposure path than the `.env` file itself** — scrubbing `.env` and wiring the vault
does nothing to a value that was ever typed into or executed by the agent in a prior session. Any
future Agent Vault cutover should treat "does the agent's own history/state store contain this
value" as its own explicit check, not assumed covered by the `.env`-focused sweep. This is
speculative but plausible for OpenClaw/dfw too (its Anthropic key may have been set up the same
way) — unverified, since Claude Code cannot touch `/home/openclaw` at all (see
`feedback_no_claude_code_home_openclaw_access`); worth Olu or Will checking directly.

**A second, self-inflicted risk found during that same sweep**: a bounded-context `grep -o
'.{0,N}KEYNAME.{0,M}'` search (used to inspect *what* is adjacent to a credential-name match
without printing a whole file) is not automatically safe — a context window wide enough to be
useful for reading structure is also wide enough to capture and print part of a real secret if
one happens to be there, and seven clean/metadata-only files in a row provide no guarantee the
eighth is also clean. This is a variant of the "pattern-matched redaction has the identical
failure mode for anything it doesn't expect" lesson in global CLAUDE.md — check for an explicit
redaction marker (`grep -c REDACTED`) or a byte-length/format heuristic *before* revealing any
surrounding context, rather than assuming a fixed context width is safe because it has been so
far in the same sweep.

## Adding a new credential once an agent is already cut over

The heavy lift (firewall widening, CA cert, proxy env wiring) is one-time per agent host — a
*new* credential for an already-wired agent is cheap:

1. **Never type the real value into a chat with the agent itself** — that's exactly the exposure
   path in the gap above. Set it directly via the vault CLI, run by a human on the vault host.
2. `agent-vault vault service add --vault <v> --name <svc> --host <host> --auth-type ...` (check
   `agent-vault catalog --json` first for a known provider's real header shape).
3. `agent-vault vault credential set KEY=<value>` on the vault host, never relayed through the
   agent.
4. Add only the placeholder to the agent's own env file (e.g. `NEW_KEY=__new_key__`) — the
   existing `HTTPS_PROXY`/firewall wiring already covers any new outbound **public-internet**
   host, no repeat of the firewall/CA/systemd phases. **If the new host is internal/tailnet-only
   (not on the public internet), see "netguard blocks private IP ranges by default" below first**
   — it needs one more step the public-host case doesn't.
5. Restart the agent's gateway service to pick up the new placeholder.

## netguard blocks private/internal IP ranges by default — a real gap for tailnet-only services

Agent Vault has a built-in SSRF-protection layer ("netguard", undocumented in the top-level
README/guides as of 2026-09-01 — found by grepping symbol strings out of the binary, confirmed
via `docs.agent-vault.dev/self-hosting/environment-variables.md`) that blocks the MITM proxy from
dialing private/reserved IP ranges (RFC-1918, loopback, link-local, IPv6 ULA, **CGNAT — this
includes Tailscale's own `100.64.0.0/10` range**) by default
(`AGENT_VAULT_ALLOW_PRIVATE_RANGES=false`). Cloud metadata endpoints stay blocked regardless of
this setting. Every credential this project brokered before Home Assistant (Anthropic, OpenAI,
Groq, LunaRoute, Telegram) was a public-internet host, so this never came up — the first
tailnet-only service hit it immediately, producing a plain `502` on the client side with **no
hint in the default-level logs at all**. Confirmed live 2026-09-01 (hermes-agent → Home
Assistant, `homeassistant.tail922cee.ts.net` → `100.116.152.84`), full incident in
[[project_agent_vault_hermes_migration]].

**Diagnosis**: bump logging to see it — add a temporary systemd drop-in
(`ExecStart=` cleared then re-specified with `--log-level debug`), `daemon-reload`, restart,
reproduce the failing request, then `journalctl -u agent-vault`. The real error only shows at
debug level: `netguard: connection to <host> (<ip>) blocked by network policy`. Remove the
drop-in and restart back to normal (default `info`) once diagnosed — debug level logs full
per-request proxy details continuously, not something to leave on.

**Fix**: add the destination's IP to `AGENT_VAULT_NETWORK_ALLOWLIST` in
`/root/.config/agent-vault.env` on the broker host (comma-separated bare IPs or CIDRs — this env
var is only consulted when `AGENT_VAULT_ALLOW_PRIVATE_RANGES=false`, the correct default to leave
alone). **Allowlist the specific IP, not the whole Tailscale CGNAT range** — a shared
multi-tenant broker instance serving more than one agent/vault (this project's does: `dfw` +
`hermes`) shouldn't have its SSRF protection loosened tailnet-wide just because one service on
one vault needs one internal host; that defeats the point of the guard for every other vault on
the same instance. Restart `agent-vault.service` to apply. Tailscale IPs are normally stable
per-device, but a future identity-churn event (device remove/re-add — see the
`tailscale-pihole-dns-routing` skill) could change it, requiring the allowlist entry to be
updated to match.

**Any future internal/tailnet-only credential on any vault on this broker needs this same step**
— it's not specific to Home Assistant, just the first time this category of destination was
exercised.

## Claude Code's own classifier and this workflow

Editing an *existing* credentials `.env` file (even to swap one value for a placeholder) reliably
trips Claude Code's own auto-mode safety classifier, regardless of encoding — ask the human to
run that one command themselves rather than retrying. A plain `cp` for backup/restore of the
same file is not blocked (it's not writing new/modified content). Creating a brand-new file
(e.g. a fresh `AGENT_VAULT_TOKEN`/`ADDR`/`VAULT` env file) has not been observed to trip it.

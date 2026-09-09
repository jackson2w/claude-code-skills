---
name: claude-code-remote-control-host
description: This skill should be used when building, debugging, or extending a persistent Claude Code Remote Control server host — a Linux box (LXC/VM/VPS) that runs `claude remote-control` under systemd as a dedicated service user so sessions can be driven from the Claude mobile app or claude.ai/code and survive the laptop closing — including the login/auth model, per-project systemd template units, the liveness watchdog, and fleet SSH access for the service user. Built once for the homelab (`claude-code`, VMID 112, 2026-09-09). Trigger phrases include "claude remote-control", "remote control server systemd", "claude-rc@", "Remote Control requires a full-scope login token", "You must be logged in to use Remote Control", "setup-token remote control", "CLAUDE_CODE_OAUTH_TOKEN remote control", "refreshTokenExpiresAt", ".credentials.json expiresAt", "remote control journal spam", "claude remote-control --help hangs", "list-unit-files template instance", "systemctl show --value order", "git ls-remote -h HEAD", "Enable Remote Control? (y/n)", "hasTrustDialogAccepted", "workspace trust headless", "claude-rc-watchdog", "claude-code-install.yml", "claude_code_pubkey".
---

# Claude Code Remote Control host

A persistent `claude remote-control` server on an always-on Linux host, one server process per
project, each a systemd template instance running as a low-privilege service user. Sessions are
created and driven from the Claude mobile app or claude.ai/code; execution and files stay on the
host. Reference build: `claude-code` (unprivileged Debian 13 LXC, VMID 112, `192.168.50.231`),
Terraform `claude-code.tf`, Ansible `claude-code-install.yml` + `claude-rc-watchdog.sh` in
`homelab-ansible`. Design record: the homelab planning repo's
`archive/claude-code-homelab-architecture-proposal.md`; state in `project_claude_code_rc_host`
memory. This skill is the durable "how" and every trap hit building it.

## 1. Facts that shape the design (verified against the docs and live, 2026-09-09)

- **Auth is a browser login, full stop.** Remote Control needs the full-scope claude.ai
  `/login`. A `claude setup-token` / `CLAUDE_CODE_OAUTH_TOKEN` credential is refused by design
  ("can only make model requests"); `ANTHROPIC_API_KEY` disqualifies it too. So a headless host
  needs **one interactive step by the account owner**, as the service user, over SSH: `claude`,
  `/login` (paste the code the browser shows), finish onboarding, `/exit`. Plan for it; don't
  try to script around it.
- **Two more one-time prompts** exist: the workspace-trust dialog per project directory, and
  "Enable Remote Control? (y/n)" on the first `claude remote-control`. Trust can be pre-seeded
  (§3); the RC confirmation is answered once interactively (`claude remote-control` once, `y`,
  Ctrl+C) and then remembered.
- **The login expires.** In `~/.claude/.credentials.json`, `claudeAiOauth.expiresAt` is the
  ~8-hour *access token* (auto-refreshed while a server runs); `claudeAiOauth.refreshTokenExpiresAt`
  is the real login lifetime (~28 days observed). Alert on the second. A server that outlives
  the login stops making progress silently.
- **The process runs fine without a TTY** — probed: it gets as far as the login check headless.
  Under systemd it works with no pty wrapper.
- **`claude remote-control --help` hangs on a signed-in machine**: it checks eligibility and
  starts the server rather than printing help. Take the flag list from the docs page
  (`https://code.claude.com/docs/en/remote-control`). Flags go *after* `remote-control`;
  the useful ones are `--name`, `--capacity N` (default 32), `--spawn same-dir|worktree|session`,
  `--permission-mode`.
- **Outbound-only.** Registers with the Anthropic API and polls; no inbound port, no Tailscale
  Serve endpoint to create — a documented exception to a "Serve is the standard access pattern"
  rule, not a deviation. Direct `api.anthropic.com` only (no `ANTHROPIC_BASE_URL`, no Bedrock).
- **Don't set** `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`,
  or `DISABLE_GROWTHBOOK` for the service user — each silently disqualifies Remote Control.
- **Restarting the unit resumes its relay sessions** (within ~4h of the stop). Verified: a
  restart brought the same session back on the phone. Crashed *sessions* (not the server) are
  re-served when a device sends them a message.
- No crash auto-recovery of the server itself, and the server **exits after ~10 minutes of lost
  API reachability**. systemd `Restart=always` covers both.

## 2. Host shape

- Dedicated service user (`claude`, `/home/claude`, bash shell). Native installer run *as that
  user* (`curl -fsSL https://claude.ai/install.sh | bash`, `creates: ~/.local/bin/claude`).
  Debian 13 LXC template has **no `sudo`** — install it before any `become_user` task.
- `~/projects/<name>` per project; `git clone` needs the service user's own SSH key accepted on
  GitHub (account key = every repo; deploy keys are one-key-per-repo, so that's N keypairs +
  `Host` aliases). Pin GitHub's host key and **assert the scanned fingerprint against the
  published one** (`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`) before writing it.
- Service user's global `~/.claude/CLAUDE.md` carries the session-hygiene rules (resume not
  restart, `/compact` at breakpoints, `/rename`, the env-var bans above) so they re-establish
  every session.
- `~/.ssh/config` for the service user: right login per fleet host, `StrictHostKeyChecking
  accept-new` so a first connection never stalls a phone-driven session.

## 3. Per-project systemd template unit

```ini
[Unit]
Description=Claude Code Remote Control server for project %i
After=network-online.target tailscaled.service systemd-resolved.service
Wants=network-online.target
ConditionPathExists=/home/claude/.claude/.credentials.json
ConditionPathIsDirectory=/home/claude/projects/%i
StartLimitIntervalSec=30min
StartLimitBurst=6

[Service]
User=claude
Group=claude
WorkingDirectory=/home/claude/projects/%i
Environment=HOME=/home/claude
Environment=PATH=/home/claude/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=LANG=en_US.UTF-8
ExecStart=/home/claude/.local/bin/claude remote-control --name %i --capacity 4
StandardOutput=null
StandardError=journal
Restart=always
RestartSec=30s
KillMode=mixed
TimeoutStopSec=30s

[Install]
WantedBy=multi-user.target
```

- **`ConditionPathExists` on the login file** keeps instances *inactive* (a skip, not failed,
  not restart-looping) until the owner's login exists. Enable them in Ansible without
  `state: started`; a separate task starts them `when` the login file exists.
- **Do NOT gate on `projects/%i/.git`.** A server over an empty directory is still a usable
  session; gating on the checkout took a live server down mid-use. Report "no checkout yet"
  from the watchdog instead.
- **`StandardOutput=null` is load-bearing.** With stdout not a TTY the status panel redraws
  continuously — measured ~5 journal lines/second, ~400k/day. Errors (including the
  login-expired message) go to stderr and stay in the journal.
- Pre-seed workspace trust so a TTY-less server can start in each directory: set
  `projects["<abs dir>"].hasTrustDialogAccepted = true` in `~/.claude.json` (a small Python
  script that edits only that key, prints `changed`/`unchanged`). Ansible `changed_when` must
  test the last line *exactly* — `'changed' in stdout` also matches "unchanged".
- Default permission mode is the human backstop: every command a phone-driven session runs
  prompts on the phone. Enable **Push when actions required** in `/config` so the prompt is a
  notification. Changing `--permission-mode` is a deliberate playbook edit, never a session's.

## 4. Watchdog (report-only, diff-alert)

`claude-rc-watchdog.sh` on the controller, every 15 min, one SSH round-trip as root:

- Enabled instances: read the **`/etc/systemd/system/multi-user.target.wants/claude-rc@*.service`
  symlinks**. Enabled template *instances* do not appear in `systemctl list-unit-files`, and
  never-started ones aren't loaded for `list-units`.
- Per unit: `systemctl show -p ActiveState -p SubState -p NRestarts` **without `--value`** and
  parse `Key=Value`. `--value` prints properties in systemd's internal order, not the requested
  order — a positional `read a s n` silently got `NRestarts` in `a`.
- Login: `jq -r .claudeAiOauth.refreshTokenExpiresAt` (only that field — never the tokens);
  fail if past, warn <3 days (matches Claude Code's own warning). `expiresAt` >2h past with a
  server running = refresh failing (warn). Also `journalctl -u 'claude-rc@*' --since '20 min
  ago' | grep -ci 'login expired\|run /login\|must be logged in'` — the most direct signal.
- Restart bursts: `NRestarts` grew since the last snapshot → warn (crash or relay drop).
- Inactive unit: with no login → ok "waiting on login"; with login but no `.git` → warn "no
  checkout"; otherwise fail. Alert only on new/worsened findings; silent on recovery.

## 5. Fleet exec access for the service user (if wanted)

- Grant via the fleet baseline playbook with one `authorized_key` task, a single
  `claude_code_pubkey` var and a `present`/`absent` switch (revocation = one edit, one run).
  Target `user: "{{ ansible_user }}"` so it lands on root for the LXC/VM fleet and the admin
  account on a hand-built host.
- **Exclude the RC host itself** (`when: inventory_hostname != 'claude-code'`) — otherwise the
  unprivileged service user gets root on its own box via `ssh root@localhost`.
- Verify **positive and negative**: `sudo -u claude ssh -n -o BatchMode=yes <host> hostname`
  for granted hosts, and `Permission denied` for its own host and every excluded one. Use
  `ssh -n`; without it a loop of inner `ssh` calls silently swallows the outer script's stdout.
- Root on the controller is already root on the fleet through the controller's deploy key, so
  "controller only" narrows the *path*, not the blast radius. Say so when presenting the option.

## 6. Small traps, in the order they bit

1. `git ls-remote --exit-code -h <repo> HEAD` **never matches**: `-h` restricts to
   `refs/heads` and no branch is named HEAD. The reachability probe reported every repo
   unreachable with working auth. Drop `-h`.
2. `ansible.posix.known_hosts` reported `changed` every run with the identical key present;
   an exact-line `lineinfile` is idempotent by construction.
3. A `systemctl start` typed while still inside `sudo -iu claude` fails with
   `Failed to start …: Access denied` plus a `pkttyagent` complaint — it's the wrong user, not a
   broken unit.
4. `ssh -T git@github.com` as the service user is the definitive auth check ("Hi <user>!");
   trust it over any wrapper's verdict.
5. Restore-test coverage for this host should check the binary (`sudo -u claude
   /home/claude/.local/bin/claude --version`), not a unit: a restored clone has no network and
   the units are Condition-gated.
6. The fleet's weekly-sweep exposure arrays (`LOOPBACK_ONLY`/`LAN_OK`) have no entry for a
   host with no listener at all; that's correct, same as the Ansible controller.

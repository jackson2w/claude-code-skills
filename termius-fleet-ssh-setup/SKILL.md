---
name: termius-fleet-ssh-setup
description: This skill should be used when setting up or extending Termius as an SSH client across a fleet of mixed LXC/VM/bare-metal/VPS hosts, when adding a new host to an existing Termius setup, when building Termius Snippets or Startup Snippets for recurring diagnostic commands, when a Termius SFTP session lands in the wrong directory or the user asks how to bookmark a remote SFTP path, or when an SFTP connection silently lands in the home directory instead of the intended target directory. Trigger phrases include "termius setup", "add a host to termius", "termius snippet", "termius startup snippet", "termius broadcast", "termius workspace", "sftp default path", "sftp bookmark remote directory", "Subsystem sftp -d flag", "sftp lands in home directory instead of", "termius keychain import ssh key", "tmux new -As", "termius sftp permission denied silently falls back".
---

# Termius SSH client setup across a mixed fleet

Covers the non-obvious parts of standing up Termius (desktop or mobile) against a fleet of
hosts with varying SSH users, kernel/hardware types, and hardening postures — plus a real
gotcha in Termius' SFTP handling that has no in-app fix.

## Host import conventions

- **Address every host by its Tailscale MagicDNS name** (`<host>.<tailnet>.ts.net`), not a LAN
  IP, if the tailnet has roaming DNS set up. One host entry then works identically whether
  connecting from home or off-network — no separate LAN/Tailscale duplicate entries needed.
- **Set an explicit username on every host entry — never rely on a login prompt or a
  remembered default.** This matters most on any hardened host with fail2ban: a stray root
  login attempt against a host that only accepts a specific non-root sudo user gets the
  source IP banned by source-IP, which can then also block the *correct* subsequent attempt,
  turning a typo into a full lockout requiring out-of-band console recovery. Different hosts
  in a mixed fleet often use different users (root for most internally-hosted services, a
  dedicated non-root sudo user for an externally-hardened VPS, yet another user for a
  bare-metal box) — a per-host table avoids fleet-wide guessing:

  | Host type | Typical user |
  |---|---|
  | Proxmox-hosted LXC/VM (internal, root SSH normal) | root |
  | Hardened external VPS (fail2ban, `PermitRootLogin no`) | its documented non-root sudo user |
  | Bare-metal host built outside the Proxmox fleet | whatever account was created at build time |

- Tag/color-code hosts by risk profile (e.g. a distinct color for the one host where a wrong
  username has real lockout consequences) so it's visually obvious before connecting.
- A host with no real shell (an appliance OS with only a web UI) should **not** be added as an
  SSH host at all — keep its web URL as a plain browser bookmark instead of forcing an entry
  that will never connect.

## Keychain / identity

- Import the personal SSH private key directly into Termius' local encrypted Keychain vault
  once (enter the passphrase in-app at import time, never anywhere else), then attach that
  same key to every host entry — no per-host key duplication needed.
- Don't enable SSH agent forwarding to any host. If every host is reachable directly (e.g. over
  a mesh VPN like Tailscale), there's no bastion-hop that would need it, and forwarding an
  agent to a remote host is unnecessary exposure.
- **App-level security**: enable biometric/PIN app lock — this app holds the one key that
  reaches the entire fleet. Set host-key verification to strict/ask, never silent-accept, so a
  genuine host-key rotation (e.g. after a rebuild) prompts for confirmation rather than passing
  silently.
- **Cloud Sync is a deliberate decision, not a default.** Termius' free tier keeps the vault
  local to one device (no sync); a paid tier adds encrypted multi-device sync, which also
  means the private key replicates to Termius' cloud storage (encrypted, but still a real
  decision point given no other credential in the environment may be centralized yet). Don't
  silently enable sync — confirm the user actually wants it first.

## Snippets and Workspaces

Termius Snippets (Vault → Snippets → New Snippet, fields: **Action description**/name and
**Script**) are reusable saved commands. Running a snippet against **multiple selected hosts
simultaneously is a free-tier feature** via a Workspace's Broadcast Input (open a Workspace
grouping the target hosts, then broadcast the snippet to every pane at once) — use this
instead of manually looping the same SSH command over multiple hosts by hand.

Useful categories of snippet to build for a homelab-style fleet:
- **Diagnostic**: kernel/reboot check (see the `debian-kernel-reboot-check` skill for the
  exact command), general health (`uptime; df -h /; free -h; systemctl --failed --no-legend`),
  Tailscale sanity (`tailscale status --peers=false; tailscale debug prefs | grep -Ei
  'hostname|runssh'`), DNS resolver sanity (`readlink -f /etc/resolv.conf`), Docker health
  (`docker ps --format 'table {{.Names}}\t{{.Status}}'` on Docker-based hosts only).
- **Repo drift**: a per-host loop over known local git repo paths running `git status
  --short` — supplements, doesn't replace, any existing automated drift-check tooling.
- **Manual triggers for already-scheduled automation**: if recurring maintenance/report jobs
  already run on a timer (systemd timers, cron), add a snippet per job that just starts the
  underlying service/unit on demand (`sudo systemctl start <job>.service`) for off-schedule
  runs — get the *real* unit name from `systemctl list-timers`/`list-unit-files` rather than
  guessing, names don't always match the human-readable job description.
- **Capacity checks**: for any host with a fixed-size datastore/disk that matters (a backup
  server, a media library), a `df`-based check with the same ok/warn/fail thresholds as
  whatever automated capacity alerting already exists, so a manual check and the automated
  one always agree.

### Startup Snippets (auto-run on connect)

Termius supports a **Startup Snippet** per host: Hosts → select host → Edit → Advanced
Options → Startup Snippets. It fires ~1 second after the SSH connection is established, and
multiple startup snippets run in the order configured.

The highest-value use: auto-attach to a persistent `tmux` session so a dropped connection
(common on mobile) never loses in-progress work.

```
tmux new -As work
```

- `-s work` names the session `work`
- `-A` attaches to that session if it already exists instead of erroring — so this single
  command both creates the session on first connect and re-attaches on every connect after,
  with no branching logic needed.
- Requires `tmux` actually installed on the host first (`apt-get install -y tmux` if missing —
  check with `which tmux` before assuming it's there).
- Only worth setting on hosts where long-running or interactive work actually happens (a
  control/automation node, a host reached mostly from mobile) — setting it on every host in
  the fleet just adds noise for quick admin dips that don't need session persistence.

## SFTP default landing directory (no built-in bookmark feature)

**Termius has no remote-path bookmark/favorite feature.** Don't assume one exists based on
general SSH-client conventions — verify against Termius' own current documentation before
telling a user where to find it, since this has been incorrectly assumed to exist before. The
actual supported mechanism is entirely server-side, via `sshd_config`.

### The mechanism

Find the `Subsystem sftp ...` line in `/etc/ssh/sshd_config` and append a `-d "<path>"` flag:

```
Subsystem	sftp	/usr/lib/openssh/sftp-server -d "/path/to/land/in"
```

The sftp-server binary path varies by distro (Debian: `/usr/lib/openssh/sftp-server`; some
other distros: `/usr/libexec/sftp-server`) — **read the existing line first**, don't paste in
an example path from documentation and assume it matches.

### Safe procedure

```bash
# 1. Back up first
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak-$(date +%Y%m%d)

# 2. Confirm the exact current line before editing
grep -n '^Subsystem' /etc/ssh/sshd_config

# 3. Append the -d flag to that exact existing line (sed example — adjust to the real path found above)
sudo sed -i 's|^Subsystem\tsftp\t/usr/lib/openssh/sftp-server$|Subsystem\tsftp\t/usr/lib/openssh/sftp-server -d "/target/path"|' /etc/ssh/sshd_config

# 4. Validate the config before restarting anything
sudo sshd -t && echo "config OK"

# 5. Confirm the real service unit name first -- Debian commonly uses `ssh.service`, not `sshd.service`
systemctl list-units --type=service | grep -E '^\s*ssh(d)?\.service'
sudo systemctl restart ssh.service

# 6. Verify plain SSH still works (config error would break this, not just SFTP)
ssh -o ConnectTimeout=5 <user>@<host> "echo ssh ok"

# 7. Verify the actual SFTP landing directory -- service-active is not proof this worked
sftp -o ConnectTimeout=5 -b - <user>@<host> <<< 'pwd'
```

### Gotchas

- **Only one default path per host** — a single `Subsystem` line means a host with multiple
  plausible target directories (e.g. two different data sets an admin browses) can only
  default to one. Pick the more frequently used one; the other is still reachable by typing
  its path manually once connected.
- **Before hand-editing `sshd_config` on any Ansible/Terraform-managed host, check whether
  it's already templated by existing IaC.** A future playbook run that manages the same file
  could silently revert a hand-edit. Grep the IaC repo for `sshd_config` and read exactly
  which lines/directives it manages (e.g. it may only touch `PasswordAuthentication`/
  `PermitRootLogin` and never the `Subsystem` line, in which case a hand-edit to `Subsystem`
  is safe from that particular playbook) — don't assume either way without checking.
- **SFTP has no sudo.** The connecting user needs genuine filesystem read+execute permission
  on the target directory and every parent directory in the path. If the target is owned by a
  different user/group with a restrictive mode (e.g. `750` owned by a service account the
  connecting user isn't a member of), the `-d` flag doesn't error — **the SFTP session
  silently falls back to the connecting user's home directory** instead. This looks like the
  `-d` flag didn't take effect, but it's a permissions problem, not a config problem. Diagnose
  with:
  ```bash
  namei -l /target/path        # shows the full permission chain down to the target
  groups <connecting-user>     # confirm group membership against the target's owning group
  ```
  Fix by adding the connecting user to the owning group (`usermod -aG <group> <user>`) if the
  group bit already grants the needed access (e.g. `r-x` for read-only browsing — this does
  *not* grant write if the group bit lacks `w`). **A fresh SFTP session is required to pick up
  new group membership** — an already-open connection or one immediately retried in the same
  shell session won't reflect it; reconnect cleanly before concluding the fix didn't work.

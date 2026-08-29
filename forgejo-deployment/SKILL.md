---
name: forgejo-deployment
description: This skill should be used when installing or debugging a self-hosted Forgejo (Gitea fork) git server as a native binary + systemd service — not Docker. Covers the three required secrets (SECRET_KEY/INTERNAL_TOKEN/JWT_SECRET) and the permission-denied crash-loop from a locked-down config file, unattended install without exposing the web setup wizard, why Forgejo's built-in git-SSH server needs firewall-level scoping instead of an app-level bind address, a non-obvious API scope requirement for repo deletion, and Vultr Block Storage's region-locking. Trigger phrases include "forgejo install", "forgejo systemd", "forgejo app.ini", "JWT_SECRET failed loading", "save oauth2.JWT_SECRET failed", "forgejo not supposed to be run as root", "forgejo admin user create", "forgejo random-password", "forgejo generate secret", "forgejo INSTALL_LOCK", "forgejo git-ssh port", "forgejo delete repo API 403", "write:user scope forgejo", "vultr block storage wrong region", "no active instances available in this region", "vultr NVMe block storage not available".
---

**Status note (2026-08-24): the `dfw` instance this skill documents was decommissioned** — it
was live 2026-08-16 through 2026-08-24 but had zero repos, pushes, clones, or logins in its
entire log history (every real repo went to GitHub instead). Torn down: service, binary, `git`
user, Tailscale Serve mapping, `ufw` rules, and the dedicated Vultr Block Storage volume all
removed. See `project_dfw_vultr_buildout` memory for the full decommission record. This skill's
technical content below is kept as-is for any future redeploy — nothing here needs correcting,
it just isn't live right now.

## Version — verify, don't assume

Check `forgejo.org/releases` (or `code.forgejo.org/forgejo/forgejo/releases`) for the current
stable tag before installing — don't reuse a version number from a prior session/training data.
Download the binary **and its `.sha256` file**, verify before installing:

```bash
VERSION="16.0.2"  # confirm current at forgejo.org/releases
wget -q "https://code.forgejo.org/forgejo/forgejo/releases/download/v${VERSION}/forgejo-${VERSION}-linux-amd64"
wget -q "https://code.forgejo.org/forgejo/forgejo/releases/download/v${VERSION}/forgejo-${VERSION}-linux-amd64.sha256"
sha256sum -c "forgejo-${VERSION}-linux-amd64.sha256"
sudo install -m 755 "forgejo-${VERSION}-linux-amd64" /usr/local/bin/forgejo
```

## Three secrets are required, not two

`app.ini`'s `[security]` section needs `SECRET_KEY` and `INTERNAL_TOKEN` — but oauth2 also needs
its own `[oauth2]` `JWT_SECRET`, easy to miss since it's a separate config section and the docs
don't always group all three together. Generate all three the same way, redirected straight to a
file (never printed — same discipline as any other credential):

```bash
sudo -u git bash -c '/usr/local/bin/forgejo generate secret SECRET_KEY > /tmp/secret_key.txt'
sudo -u git bash -c '/usr/local/bin/forgejo generate secret INTERNAL_TOKEN > /tmp/internal_token.txt'
sudo -u git bash -c '/usr/local/bin/forgejo generate secret JWT_SECRET > /tmp/jwt_secret.txt'
```
(`wc -c` the files to confirm non-empty — `wc -l` can misleadingly report 0 since these values
have no trailing newline, not because the file is empty.)

**If `JWT_SECRET` is left unset**, Forgejo doesn't fail cleanly — it tries to *auto-generate one
and write it back into `app.ini`* on every startup:
```
[oauth2] JWT_SECRET or JWT_SECRET_URI failed loading: invalid base64 decoded length: 0, expects: 32 - creating new key
[F] save oauth2.JWT_SECRET failed: failed to save "/etc/forgejo/app.ini": open /etc/forgejo/app.ini: permission denied
```
If `app.ini` is deliberately locked down (e.g. `root:git 640` so the running `git` user can read
but not write its own config — the correct posture, not a bug) this write-back fails and the
service crash-loops (`Start request repeated too quickly` after 5 rapid restarts). Fix: generate
`JWT_SECRET` explicitly upfront like the other two, append it under `[oauth2]` before first start,
never rely on the auto-write-back path.

## Unattended install — never expose the setup wizard

Set `INSTALL_LOCK = true` in `app.ini` from the start (with `DB_TYPE`/`PATH` and all three secrets
already filled in) so the interactive web installer never runs, not even for a moment. Create the
first (admin) account via CLI instead of the web wizard:

```bash
sudo -u git bash -c 'export GITEA_WORK_DIR=<data-dir>; /usr/local/bin/forgejo admin user create \
  --config /etc/forgejo/app.ini --admin --username <user> --email <email> \
  --random-password > /tmp/forgejo-admin-create.log 2>&1'
```
`--password-file` is **not** a valid flag on this CLI (only `--password` for a literal value or
`--random-password` to have Forgejo generate one) — redirect `--random-password`'s output to a
file rather than letting it print to a shared terminal/tool output, then have the actual account
owner retrieve and delete that file themselves.

## Git-SSH: the built-in server ignores `HTTP_ADDR`-style restriction

`START_SSH_SERVER = true` + `SSH_PORT`/`SSH_LISTEN_PORT` (use a non-standard port like `2222` if
the host already runs a real system sshd on 22 for admin access — avoids fighting with the system
sshd's `authorized_keys` command-wrapping approach for a second SSH identity) binds to **all
interfaces** regardless of what `HTTP_ADDR` is set to for the web UI — there is no equivalent
bind-address setting for the SSH listener. Reachability must be scoped at the firewall layer
instead:

```bash
sudo ufw allow in on tailscale0 to any port 2222 proto tcp comment 'forgejo git-ssh, tailnet only'
```

Verify **both directions** (same discipline as any other Tailscale-scoped service): refused from
outside the tailnet (`nc -zv <public-ip> 2222` times out), reachable via the Tailscale IP
(`nc -zv <tailscale-ip> 2222` succeeds). Clone URL when the SSH port isn't 22:
`ssh://git@<domain>:<ssh-port>/<owner>/<repo>.git` (the `ssh://` scheme + explicit port, not the
short `git@host:owner/repo.git` form, which assumes port 22).

SSH clone/push needs a public key registered to the account first (Settings → SSH/GPG Keys →
**"Manage SSH keys"** section specifically, not the GPG one right below it — easy to click the
wrong "Add key" button since both sections look identical at a glance) — there's no anonymous
SSH access even to a repo the same user owns.

## API gotcha: deleting a repo needs `write:user` scope, not `write:repository`

A token minted with `--scopes write:repository` gets a `403` calling `DELETE
/api/v1/repos/{owner}/{repo}`:
```
{"message":"token does not have at least one of required scope(s): [write:user]"}
```
Mint cleanup/admin tokens with `--scopes write:repository,write:user` if repo deletion is part of
what they'll be used for. Also: **there is no `forgejo admin user delete-access-token` CLI
command** (only `generate-access-token` exists) — revoke a token via the web UI (Settings →
Applications) or the API's own token-management endpoint; a short-lived cleanup token left over
after a one-off script isn't a real risk (scoped to one account) but isn't self-cleaning either.

## Running as root fails fast and loud (this is correct)

`forgejo admin user list` (or any subcommand) run as `root` instead of the configured `RUN_USER`
refuses outright: `Forgejo is not supposed to be run as root ... use setcap and
cap_net_bind_service`. Always `sudo -u <run-user> ...` for CLI operations, matching whatever
`RUN_USER`/`User=` the systemd service itself uses.

## Vultr Block Storage is region-locked — check before creating, not after

A Block Storage volume can only attach to an instance in the **same Vultr datacenter/region**.
Symptom if mismatched: the dashboard's attach flow shows *"No active instances available in this
region to attach to"* with no instance picker at all — not an error on the instance, a genuine
"this volume physically cannot go here" state with no workaround short of destroying and
recreating in the right region.

Two things worth confirming *before* creating the volume, not after:
- The instance's actual region (Vultr's `dfw` location code is Dallas — a hostname that looks
  like a location code is a strong hint, but confirm rather than assume).
- **NVMe Block Storage isn't offered in every region** — it may simply not appear as a creatable
  option for the instance's actual datacenter. **HDD Block Storage has broader regional
  availability and is ~4x cheaper per GB** ($1/40GB vs $1/10GB for NVMe) — a reasonable choice by
  default for a single-user, low-traffic workload where disk latency won't be the bottleneck
  (network/protocol overhead dominates for occasional personal use), not just a fallback when NVMe
  isn't available.

Volumes can be **resized up later** (dashboard, CLI, or Terraform) but never shrunk — no need to
overprovision "just in case" up front if growing later is genuinely just a resize + filesystem
extend with no data migration.

---
name: standalone-ansible-repo
description: This skill should be used when creating an Ansible control repo for a single hardened, non-fleet host (a VPS, a standalone server) that should not get a new privileged SSH bridge from an existing LAN Ansible controller, or when retrofitting a live, hand-configured host into version-controlled Ansible without a risky big-bang rewrite. Trigger phrases include "bring this host under ansible", "ansible repo for a vps", "ansible without a control node", "ansible_connection=local", "retrofit ansible on a live host", "graduation catalog for a new host", "mirror homelab-ansible's pattern on another host", "should ansible-ctrl push to this host", "local connection ansible playbook".
---

# Standalone-host Ansible repo pattern

Use this when a host needs real, version-controlled Ansible management but does not belong to
an existing LAN fleet with a dedicated control node — a public VPS, a hardened standalone
server, anything outside that fleet's trust boundary. Built 2026-08-19/20 for `dfw-ansible`
(the `dfw` Vultr dev server), mirroring the sibling fleet repo `homelab-ansible`'s shape but
adapted for the one real difference: how it connects.

## Decide the connection model first — this is the one real design choice

`homelab-ansible` pushes from a dedicated control node (`ansible-ctrl`) to LAN hosts over SSH
as root, because every host in that fleet already trusts `ansible-ctrl` with that level of
access. A standalone host usually does not fit this: it is hardened differently (no root SSH,
a key-only sudo user, SSH restricted to a VPN/tailnet), and the existing controller typically
has zero privileged access to it (at most a narrow no-sudo key for read-only drift checks).

Making the controller push to it anyway means minting a new SSH keypair + broad NOPASSWD sudo
grant, bridging a LAN control node into a public-facing host — a real new privilege grant, not
a config detail. Don't do this by default. Instead, **run the repo locally on the host itself**
(`ansible_connection=local`) — the host plays its own control-node role, invoked the same way
its config has always been managed (a direct root/sudo session on the box, whether interactive
or via a Claude Code session connecting to it). No new cross-host trust is created; the
existing controller's relationship to the host is unchanged.

Only push from a shared controller if the host already grants that controller privileged
access for an unrelated reason, or if centralizing management of many identical standalone
hosts is the actual goal — the point here is one host, not a second fleet.

## Repo structure

Mirror the sibling fleet repo exactly:

```
<name>-ansible/
  README.md         # what runs where, how it connects, secrets policy
  CATALOG.md         # graduation catalog — see below
  ansible.cfg         # inventory = inventory.ini, host_key_checking = False
  inventory.ini        # single host, ansible_connection=local
  .gitignore
  playbooks/
    <service>-install.yml
    files/
    templates/
    scripts/
      lib/
```

`inventory.ini` for a single local-connection host — do not wrap it in a `[group]` section
named the same as the host; Ansible warns "Found both group and host with same name" and it
serves no purpose here:
```
<hostname> ansible_connection=local ansible_python_interpreter=auto
```
Playbooks target `hosts: <hostname>` (not `hosts: localhost`) for readability parity with the
fleet repo's `hosts: <group>` convention.

## The graduation-catalog convention

A live standalone host almost always already has several hand-configured subsystems by the
time this repo gets built. Retrofitting all of them into playbooks in one pass is real risk on
a live host — don't. Instead:

1. Scaffold the repo skeleton and write `CATALOG.md`, seeded at creation time with **every**
   subsystem already live, each marked `ad-hoc` (working, not yet playbook-backed) — same
   status vocabulary as `homelab-ansible/CATALOG.md` (`ad-hoc` / `proposed` / `graduated`).
   This documents the retrofit backlog transparently without requiring it all built at once.
2. Pick one small, self-contained, low-risk subsystem to graduate first — something already
   touched recently is a good choice since its current state is fresh and provable. Write that
   one playbook to encode **exactly** what is already live, not an improved version of it.
3. Graduate the rest incrementally in later sessions, one playbook at a time, same discipline.

## Bootstrapping steps

1. Create the GitHub repo (private, matching the sibling repo's convention for infra-detail
   repos) from wherever `gh` is already authenticated.
2. On the target host: mint a dedicated ed25519 deploy key (`ssh-keygen -t ed25519 -f
   ~/.ssh/github_deploy_<name>-ansible -N ""`), add a `Host` alias in that host's own root SSH
   config pointing at it — mirrors the fleet controller's one-keypair-per-repo convention
   (GitHub deploy keys are strictly one-key-per-repo).
3. Add the public key as a **read-write** deploy key via `gh api repos/<owner>/<repo>/keys` —
   this host is the sole pusher.
4. `git clone` the repo directly onto the target host (e.g. `/root/ansible`), build the
   structure above in that working tree.
5. Check whether `ansible` itself is installed on the host (`apt-cache policy ansible` on
   Debian/Ubuntu — usually a plain `apt install`, no exotic setup needed for local connection)
   and whether the account that will run `become: yes` already has passwordless sudo
   (`sudo -n true`) — if not, playbooks need `--ask-become-pass` or a vaulted password.

## Verification discipline

Because the first playbooks describe a host that is already live and working, prove they
change nothing before trusting them:

1. `ansible-playbook ... --check --diff` — expect a clean diff. **Known false-failure mode**:
   a task chain like `get_url` → `unarchive` fails under `--check` because the download never
   actually happened in check mode, so the extract step's source file genuinely does not
   exist. This is not a real problem — it is specific to multi-step tasks with a real
   filesystem dependency between them; re-run for real to confirm.
2. Run for real (no `--check`) and expect **zero `changed`** tasks for anything meant to match
   already-live state — any `changed` here means the playbook encoded something wrong (a
   directory mode guessed instead of checked, a stale file path), not a successful retrofit.
   Fix and re-run until it reports clean.
3. Diff the deployed artifact against the playbook's own source copy of it — confirms the
   playbook is the actual live source of truth, not just superficially similar.

## A file-transfer gotcha specific to this workflow

Building and iterating on these playbooks/scripts usually means repeatedly pushing file
content to the target host over SSH (no full `git push`/`pull` round-trip for every small
edit). **Never chain two `sudo tee <file> >/dev/null && sudo tee <file2> >/dev/null` calls off
one piped stdin** — the first `tee` consumes the entire input, so the second silently writes an
empty file with no error at any step. Use a separate `cat local_file | ssh host "sudo tee
<file>"` invocation per destination file, or `tee file1 file2` in a single call if both targets
should get identical content. See the homelab CLAUDE.md's general SSH/remote-automation
gotchas for the sibling issue with backticks/`$()` inside a double-quoted SSH argument.

## Reference implementation

`dfw-ansible` (github.com/jackson2w/dfw-ansible) — `restic-backup-install.yml` and
`package-check-install.yml` are the concrete worked examples of grading a live subsystem into
a playbook using exactly this discipline. See the `project_dfw_vultr_buildout` memory for the
narrative and the `homelab-ansible/CATALOG.md` convention this was adapted from.

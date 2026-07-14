---
name: proxmox-ansible-provisioning
description: This skill should be used when creating a new Proxmox LXC (pct create) or VM, writing or debugging Ansible playbooks that target Proxmox/Debian hosts (including Debian 13/trixie), or troubleshooting a Proxmox+Ansible workflow — a "storage 'local-lvm' does not exist" error, a "Systemd 257 detected" nesting warning, Ansible failing with a locale error inside a fresh LXC, an Ansible lineinfile task that keeps reporting changed on every run, writing multi-line config/YAML files to a remote host over SSH, an "apt-key or gpg binary is required" error from Ansible's apt_repository module, a Proxmox-family product (PVE/PBS/PMG) apt install failing with a 401 against enterprise.proxmox.com, or Tailscale/anything needing `/dev/net/tun` stuck crash-looping inside an unprivileged LXC. Trigger phrases include "pct create", "pvesm status", "local-lvm", "local-zfs", "unprivileged LXC", "nesting=1", "Ansible could not initialize the preferred locale", "lineinfile idempotency", "ansible-playbook --check failing", "pct exec", "apt-key deprecated", "apt_repository module failed", "enterprise repo 401 unauthorized", "pbs-enterprise.sources", "/dev/net/tun does not exist", "tailscaled activating auto-restart", "TUN passthrough LXC".
version: 0.1.0
---

# Proxmox + Ansible Provisioning

A repeatable sequence and five real gotchas hit while building a Proxmox LXC and Ansible control
node from scratch. Each looked like a one-off problem at first; all five recur on every future
Proxmox/Ansible build unless checked for up front.

## Provisioning sequence — check reality before writing commands

Don't guess storage/template names from memory or generic Proxmox examples — verify against the
actual host first, every time:

```bash
pvesm status                    # real storage identifiers — NOT always "local-lvm"
pveam update && pveam available | grep debian-13
pveam list local | grep debian-13   # real template filename, exact version string
```

A ZFS-based Proxmox install uses something like `local-zfs`, not the LVM-thin default
(`local-lvm`) most tutorials assume. Guessing wrong here fails the `pct create` outright — cheap
to avoid by checking first.

Create unprivileged, DHCP-addressed (not a hardcoded IP — add a router DHCP reservation instead,
once you have the MAC from `ip a` inside the container):

```bash
pct create <vmid> local:vztmpl/<exact-template-filename> \
  --hostname <name> \
  --unprivileged 1 \
  --cores 1 --memory 1024 --swap 512 \
  --rootfs <real-storage-name>:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --onboot 1 \
  --ssh-public-keys /path/to/pubkey-file-on-the-host
```

## Gotcha 1 — Debian 13 (trixie) LXCs need `nesting=1` or systemd can leave services degraded

`pct create` prints `WARN: Systemd 257 detected. You may need to enable nesting.` — this is real,
not boilerplate. Systemd 257's sandboxing directives can fail inside an unprivileged LXC without
nesting enabled, leaving services silently failed/degraded on boot. Fix before first boot:

```bash
pct set <vmid> --features nesting=1
pct start <vmid>
pct exec <vmid> -- systemctl --failed   # confirm zero failed units
```

This does **not** compromise the container's unprivileged status — nesting is a separate feature
flag, not a privilege escalation.

## Gotcha 2 — fresh templates have no locale generated; Ansible hard-fails on this (not just warns)

Most commands run via `pct exec` on a bare template only print a harmless
`setlocale: LC_ALL: cannot change locale` warning. Ansible is different — it refuses to run at
all: `ERROR: Ansible could not initialize the preferred locale: unsupported locale setting`. Fix
once, system-wide, before installing Ansible:

```bash
pct exec <vmid> -- apt install -y locales
pct exec <vmid> -- sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
pct exec <vmid> -- locale-gen
pct exec <vmid> -- update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
```

## Gotcha 3 — multi-line file writes over SSH/`pct exec` can get silently corrupted

Pasting a heredoc into a remote shell can pick up extra indentation or lose the terminator
(terminal-dependent bracketed-paste issue, seen with Ghostty specifically). The write "succeeds"
with silently wrong content — easy to miss without checking. **Avoid entirely: base64-encode the
file locally and write it as a single line**, which has no embedded newlines to mangle:

```bash
base64 -i local-file.yml | tr -d '\n'
# then, on the target:
pct exec <vmid> -- bash -c 'echo <base64-blob> | base64 -d > /path/to/file.yml'
```

Always `cat` the written file back afterward to confirm it matches before trusting it — this
silent-corruption failure mode is exactly the kind of thing that looks fine until you check.

## Gotcha 4 — Ansible `lineinfile` regex anchored with `\b` matches more than intended

`\b` (word boundary) fires at *any* word-to-non-word transition, including a hyphen. A regexp like
`'MySetting\b'` also matches `MySetting-WithSuffix` — a real, different config key. Since
`lineinfile` acts on the *last* matching line by default when multiple lines match, this can
silently overwrite the wrong setting, and because the file shape keeps changing, it presents as
persistent non-idempotency (`changed` on every single run) rather than an obvious one-time bug.

Fix: anchor precisely enough to exclude sibling keys — e.g. require trailing whitespace or a
quote character immediately after the setting name, not just `\b`:

```yaml
# BAD — also matches "Automatic-Reboot-WithUsers" and "Automatic-Reboot-Time"
regexp: '^//?\s*Unattended-Upgrade::Automatic-Reboot\b'

# GOOD — requires whitespace right after, which the suffixed variants don't have
regexp: '^//?\s*Unattended-Upgrade::Automatic-Reboot\s'
```

If a `changed=1` won't go away across repeat idempotent runs, read the actual `--diff` output
(not just the recap) — it will show you exactly which line is being touched and usually reveals
this pattern immediately.

## Gotcha 5 — `ansible-playbook --check` will report false failures for dependent tasks

A task that edits a config file created by an *earlier task in the same play* (e.g. editing a
package's shipped config file right after installing that package) will fail in `--check` mode
with something like `Destination ... does not exist`. This isn't a bug — check mode doesn't
actually perform the install, so the file genuinely isn't there yet to edit. Don't chase this as a
real error; either add `create: true` to make the task robust regardless, or just verify by
running for real (against a low-risk target first if the playbook touches anything sensitive).

## Gotcha 6 — Ansible's `apt_repository` module fails on Debian 13; and Proxmox-family packages auto-add a paid enterprise repo that 401s

Two related but distinct traps when installing any Proxmox-family package (PVE itself, PBS, PMG)
via Ansible on trixie:

1. `ansible.builtin.apt_repository` shells out to `apt-key`, which trixie removed entirely —
   every call fails with `Either apt-key or gpg binary is required, but neither could be found`,
   even when no `key:` parameter was passed. Don't fight the module; skip it and write the
   sources file directly instead:
   ```yaml
   - name: Add signing key (binary keyring, goes straight in trusted.gpg.d — no apt-key needed)
     ansible.builtin.get_url:
       url: https://enterprise.proxmox.com/debian/proxmox-release-{{ ansible_distribution_release }}.gpg
       dest: /etc/apt/trusted.gpg.d/proxmox-release-{{ ansible_distribution_release }}.gpg
       mode: '0644'

   - name: Add the no-subscription repo
     ansible.builtin.copy:
       content: "deb http://download.proxmox.com/debian/<pbs-or-pve> {{ ansible_distribution_release }} <component>-no-subscription\n"
       dest: /etc/apt/sources.list.d/<name>-install-repo.list
       mode: '0644'
   ```

2. Installing the package itself (`proxmox-backup-server`, etc.) auto-creates a deb822-format
   enterprise repo file (e.g. `/etc/apt/sources.list.d/pbs-enterprise.sources`) pointed at
   `enterprise.proxmox.com`, which requires a paid subscription key and 401s on every
   `apt update` otherwise — this breaks not just this install but every subsequent idempotent
   re-run of the playbook. Disable it explicitly, before the package-install task so the first
   run doesn't fail either:
   ```yaml
   - name: Disable the enterprise repo (needs a paid subscription key, 401s otherwise)
     ansible.builtin.file:
       path: /etc/apt/sources.list.d/pbs-enterprise.sources   # filename varies per product
       state: absent
   ```
   Check `ls /etc/apt/sources.list.d/` for the actual filename if unsure — it's `.sources`
   (deb822), not the older `.list` format, on recent installs.

## Gotcha 7 — unprivileged LXCs need explicit TUN passthrough before Tailscale (or anything else needing `/dev/net/tun`) will start

`nesting=1` alone does not grant `/dev/net/tun` access — an unprivileged LXC without this fix
gets `tailscaled` stuck in an `activating (auto-restart)` crash loop, with the real error buried
in `journalctl -u tailscaled`:

```
getLocalBackend error: createEngine: tstun.New("tailscale0"): CreateTUN("tailscale0") failed; /dev/net/tun does not exist
```

Hit repeatedly across this homelab's builds (Pi-hole, Grafana, Homepage) — it recurs on every new
unprivileged LXC that needs Tailscale, not a one-off. Fix on the Proxmox host, not inside the
container:

```bash
cat >> /etc/pve/lxc/<vmid>.conf << 'EOF'
lxc.cgroup2.devices.allow: c 10:200 rwm
lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
EOF
pct stop <vmid> && pct start <vmid>   # full stop/start required -- a restart from inside the
                                      # container does not re-read the host-side .conf
```

Verify before moving on: `pct exec <vmid> -- ls -la /dev/net/tun` should show the device, and
`systemctl is-active tailscaled` should report `active`, not `activating`.

## Verification discipline for anything SSH/auth-related

Before letting a playbook change `PasswordAuthentication`/`PermitRootLogin` or similar, verify
key-based access works *first* — a hypervisor lockout is a severe, hard-to-reverse mistake. After
applying, verify both directions explicitly, not just that the playbook exited 0:

```bash
# new path works
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no root@host echo ok

# old path is genuinely closed (force the real code path, don't just omit a flag)
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o BatchMode=yes root@host echo should-fail
```

A clean `ansible-playbook` recap is not proof the security property actually holds — read the
`--diff` output and test both the allowed and blocked path directly.

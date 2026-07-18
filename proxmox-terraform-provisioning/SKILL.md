---
name: proxmox-terraform-provisioning
description: This skill should be used when setting up the bpg/proxmox Terraform provider against a Proxmox host, creating a least-privilege Proxmox API token for Terraform, importing existing LXCs/VMs into Terraform state as a no-op baseline, creating a brand-new VM (proxmox_virtual_environment_vm) via Terraform, or configuring an LXC's device_passthrough or mount_point blocks — including a "403 ... SDN.Use" error on network_device creation, a download_file resource failing with a permissions/Sys.Modify error, the provider needing SSH access for disk import, importing an appliance-image VM (UEFI/OVMF, no cloud-init — e.g. Home Assistant OS, pfSense/OPNsense) rather than a Debian cloud image, a device_passthrough block 403ing with "only allowed for root@pam", or a mount_point's backup=false attribute not actually excluding that volume from vzdump. Trigger phrases include "bpg/proxmox", "terraform import proxmox", "pveum token add", "terraform plan -generate-config-out", "PVEVMAdmin", "proxmox_virtual_environment_container", "proxmox_virtual_environment_vm", "Terraform Proxmox provider", "import existing LXC into terraform", "SDN.Use", "qm importdisk terraform", "proxmox_download_file", "ovmf", "efidisk0", "appliance image proxmox", "haos qcow2", "device_passthrough", "only allowed for root@pam", "mount_point backup", "GPU passthrough terraform LXC", "renderD128 terraform".
version: 0.3.0
---

# Proxmox + Terraform Provisioning (bpg/proxmox)

A repeatable sequence for bringing a Proxmox host under Terraform management with the
`bpg/proxmox` provider, plus gotchas hit importing already-running LXCs as a no-op baseline and,
separately, creating brand-new VMs from scratch.

## 1. Create a scoped API token, not root

Proxmox's built-in roles cover VM/LXC lifecycle management without granting host shell access —
use them instead of `root@pam` or a custom role from scratch:

```bash
pveum user add terraform@pve --comment "Terraform (bpg/proxmox provider)"
pveum aclmod / -user terraform@pve -role PVEVMAdmin       # VM.Allocate, VM.Config.*, VM.PowerMgmt, etc.
pveum aclmod / -user terraform@pve -role PVEAuditor        # Sys.Audit, VM.Audit, Datastore.Audit
pveum aclmod /storage -user terraform@pve -role PVEDatastoreUser  # Datastore.AllocateSpace/.Audit
pveum user token add terraform@pve terraform-token --privsep 0 --output-format json
```

None of these roles include `Sys.Modify` or `Sys.Console` — confirm with
`pveum user permissions terraform@pve` before trusting it; the token should never be able to open
a host-level shell.

**Never let the token secret land in your own shell output, a chat transcript, or a log.** Pipe
it directly from creation to its destination instead of echoing it at any point — e.g. parse the
`pveum ... --output-format json` output in a script and `subprocess`/`ssh` it straight into a
gitignored, `600`-permission env file on the box that will actually run Terraform. If a step
requires printing something to confirm success, print the token *ID*, never the secret value.

Provider config then just reads from environment variables — no secrets in `.tf` files:

```bash
PROXMOX_VE_ENDPOINT=https://<pve-ip>:8006/
PROXMOX_VE_API_TOKEN=terraform@pve!terraform-token=<secret>
PROXMOX_VE_INSECURE=true   # pve's default self-signed cert; fine for LAN-only traffic
```

## 2. Import existing resources as a no-op baseline, don't hand-write the config

For LXCs/VMs that already exist and already work, use Terraform's `import` block +
config-generation rather than writing `resource` blocks from memory and hoping they match:

```hcl
import {
  to = proxmox_virtual_environment_container.pihole
  id = "pve/100"   # "<node_name>/<vmid>"
}
```

```bash
terraform plan -generate-config-out=generated.tf   # writes real attribute values Terraform read back
# review generated.tf, clean it up (see gotchas below), fold into version control
terraform apply
terraform plan   # MUST show "No changes" — this is the actual proof the import was a no-op
```

That last `terraform plan` showing zero drift is the only real verification that bringing a
resource under Terraform didn't silently change anything about the running container.

## Gotcha 1 — `operating_system.template_file_id` wants `""`, not `null`

The generated config emits `template_file_id = ""` for containers with no template reference.
Changing it to `null` (which looks more idiomatic and matches what `terraform show` reports for
the imported state) fails apply with `Error: Missing required argument` — the schema treats this
attribute as required-but-emptyable, not optional. Leave it as the generator wrote it.

## Gotcha 2 — `timeout_*` fields showing up as additions are harmless

A first `terraform plan` after import typically shows `+ timeout_clone = 1800`,
`+ timeout_create = 1800`, etc. as in-place updates. These are client-side provider operation
timeouts, not attributes stored on the Proxmox container itself — applying them doesn't touch the
running guest (confirms as `Modifications complete after 0s` with no real API side effects). Don't
mistake this for the import being non-clean; the `terraform plan` *after* apply is the real check.

## Gotcha 3 — `unprivileged` is `ForceNew`: changing it destroys and recreates the container

Proxmox has no live conversion between privileged and unprivileged LXCs. If a container was
created privileged by mistake (e.g. a `pct create` that dropped `--unprivileged 1`) and you flip
`unprivileged = true` in Terraform config expecting an in-place fix, `terraform plan` will show a
**destroy + recreate**, which wipes the container's rootfs disk. Before applying that:

- Back up the container's actual application config/data first (Terraform only manages the LXC
  shell — network, disk size, resource limits — not what's installed inside it).
- Any host-side passthrough config on the Proxmox node (e.g. TUN device passthrough for
  unprivileged LXCs — see the `proxmox-ansible-provisioning` skill) has to be redone after
  recreation, since it's tied to the container's `.conf` file, not preserved across destroy.
- If the container has its own identity in another system (VPN mesh node key, etc.), recreating
  it will register as a new device there too — plan for re-authentication, not just DNS/network
  config.
- Flag this to the human before applying — it's a real outage window for whatever the container
  serves, not a quiet config change.

## Creating a new VM (not just an LXC) hits gaps the scoped token doesn't cover

Building a `proxmox_virtual_environment_vm` from scratch (as opposed to importing an existing
LXC) surfaces problems the LXC-import workflow above never hits. Found building a Proxmox Backup
Server VM:

**Gotcha 4 — attaching a NIC to a bridge needs `SDN.Use`, which `PVEVMAdmin` doesn't grant.**
PVE 9 wraps legacy bridges (`vmbr0`) as SDN zones under the hood; creating a `network_device` on
one fails with `403 ... SDN.Use` even though `PVEVMAdmin` covers every other VM operation. Fix by
granting the scoped token `PVESDNUser` (SDN.Audit + SDN.Use only, no Allocate) at the specific
zone path: `pveum acl modify /sdn/zones/localnetwork/vmbr0 --users terraform@pve --roles
PVESDNUser`.

**Gotcha 5 — `proxmox_download_file`/`proxmox_virtual_environment_download_file` needs
`Sys.Modify`, which this token deliberately doesn't have.** Downloading an arbitrary URL
server-side is exactly the privilege the scoped token was designed to exclude — don't widen the
token for it. Stage cloud images manually instead, once, as root over SSH, into local storage's
`import` content type:
```bash
curl -sL -o /var/lib/vz/import/<name>.qcow2 <url>
```
then reference the file directly: `disk { file_id = "local:import/<name>.qcow2" }`. Skip the
download resource entirely.

**Gotcha 6 — actual VM creation (the disk-import step) needs direct root SSH to the node**, which
conflicts with a token deliberately scoped to exclude host shell access. The bpg/proxmox provider
shells out over SSH for `qm importdisk`-equivalent work when a disk references a `file_id`; there
is no way around this with API-token-only auth. Rather than configuring SSH credentials into the
provider (handing Terraform permanent host shell access), do the one-time create by hand instead:
`qm create` / `qm importdisk` / `qm set` over root SSH (the same access already used for
Ansible/manual admin), then bring it under Terraform with the same
`generate-config-out` + `import {}` no-op-import pattern from section 2 above. Ongoing lifecycle
(resize, destroy, tag changes) goes through `terraform apply` with the scoped token from that
point on — only the one-time create needs host shell.

**Gotcha 7 — `generate-config-out` needs the QEMU guest agent already running** to read back
network config, or it fails with `error waiting for network interfaces from QEMU agent`. Install
and start `qemu-guest-agent` inside the guest *before* running `generate-config-out` — Debian's
`genericcloud` cloud image does not ship it preinstalled (unlike some other distros' images).
**Not universal**, though: an appliance-image guest with no guest agent at all (see Gotcha 9)
generated its config fine anyway — this requirement seems tied specifically to reading back
network config normally supplied via cloud-init, not a hard dependency of config generation itself.

**Gotcha 8 — the experimental config generator emits some invalid or redundant fields.** Seen
in practice: `cpu.units = 0` (rejected — valid range is 1–262144; both `cpu.units` and top-level
`mac_addresses` are optional+computed, so just delete the lines rather than fixing the value), and
a `network_device.enabled = true` that a deprecation warning says to remove but the schema
currently still requires — keep it despite the warning. Expect to hand-edit generated VM config
before it applies cleanly; treat the warning `Config generation is experimental` as accurate.

## Appliance-image VMs (UEFI, no cloud-init) — a third VM shape

Sections above cover LXC-import and Debian-cloud-image VM creation. A third shape showed up
building a Home Assistant OS VM (2026-07-13): importing an official appliance `.qcow2` image
(HAOS, but the same applies to any prebuilt appliance image — pfSense/OPNsense included, relevant
for a future OPNsense-on-Proxmox build) rather than a generic Linux cloud image.

**Gotcha 9 — appliance images typically need UEFI, not the `seabios` used for Debian cloud
images**, plus no cloud-init block at all:
```hcl
bios    = "ovmf"      # not "seabios"
machine = "q35"
efi_disk {
  datastore_id      = "local-zfs"
  file_format       = "raw"
  pre_enrolled_keys = false   # Secure Boot OFF — appliance images are typically unsigned for this
  type              = "4m"
}
```
Omit the `initialization` (cloud-init) block entirely — a self-contained appliance OS ignores it,
and includes its own first-boot onboarding/setup instead. Also don't assume `qm create` defaults
`ostype`; set it explicitly (`qm set <vmid> --ostype l26` for a Linux-based appliance) before
generating config, or the generated block will show `operating_system { type = null }`, which
technically matches (no drift) but is worth fixing at creation time rather than leaving unset.

Many appliance images (e.g. Home Assistant OS's `_ova-<version>.qcow2.xz` variant) already ship
with the intended virtual disk size baked in — check with `qemu-img info` after decompressing
before assuming a post-import `qm resize` is needed; it may already be sized correctly.

## Gotcha 10 — `device_passthrough` is hardcoded to `root@pam` only, no matter how the token is scoped

Building a container that needs a passed-through host device (a GPU render node for hardware
transcoding, a USB dongle, etc.), the `device_passthrough` block looks like the natural
declarative fit:

```hcl
device_passthrough {
  path = "/dev/dri/renderD128"
  mode = "0666"
}
```

`terraform plan` accepts this fine, but `terraform apply` 403s even for a token holding
`PVEVMAdmin`:

```
Error: Container create
received an HTTP 403 response - Reason: Permission check failed
(configuring device passthrough is only allowed for root@pam)
```

This isn't a missing-privilege gap fillable by granting more roles — Proxmox hardcodes this one
operation to `root@pam` specifically, presumably because arbitrary host-device passthrough is
close enough to a host-boundary escape that it's deliberately kept out of the ACL system
entirely. Don't widen the Terraform token's privileges chasing this (there is no role that grants
it). Instead: drop `device_passthrough` from the Terraform resource, create the container without
it, then pass the device through with a manual `.conf` edit over root SSH — the same escape hatch
already used for TUN passthrough (see the `proxmox-ansible-provisioning` skill's Gotcha 7, which
generalizes to any device, not just TUN):

```bash
pct stop <vmid>
cat >> /etc/pve/lxc/<vmid>.conf << 'EOF'
lxc.cgroup2.devices.allow: c <major>:<minor> rwm
lxc.mount.entry: /dev/dri/renderD128 dev/dri/renderD128 none bind,optional,create=file
EOF
pct start <vmid>
```

Document in the `.tf` file's comments *why* the device isn't there declaratively (so a future
`terraform plan -generate-config-out` refresh doesn't lead someone to re-add it and hit the same
403 again).

## Gotcha 11 — `mount_point.backup = false` doesn't necessarily write `backup=0` into the real container config

A `mount_point` block set with `backup = false` shows correctly in `terraform plan`
(`+ backup = false`) and gets recorded in `terraform.tfstate` the same way. But the actual
resulting `mpN` line in `/etc/pve/lxc/<vmid>.conf` after `apply` can come out with **no `backup`
flag at all**:

```
mp0: local-zfs:subvol-142-disk-1,mp=/mnt/media,size=500G
```

Proxmox's own default for a *volume* mount point (as opposed to a bind-mount of an existing host
directory) is **backed-up-by-default** when the flag is absent — so this silently backs up the
full volume nightly despite Terraform state insisting `backup: false` is already in effect. This
is a real drift between what Terraform believes and what vzdump will actually do, and `terraform
plan` won't show it as drift either (state matches what Terraform wrote, it's the provider's
write-to-Proxmox step that didn't fully land).

**Don't trust the state file's `backup` attribute as proof of the real on-disk behavior for this
attribute specifically.** Verify directly after apply:

```bash
grep ^mp0 /etc/pve/lxc/<vmid>.conf   # look for `,backup=0` explicitly present
```

If it's missing, fix with a direct `pct set`, which does write the flag correctly:

```bash
pct set <vmid> -mp0 local-zfs:subvol-<vmid>-disk-1,mp=/mnt/media,size=500G,backup=0
```

Confirm the fix by actually triggering a backup (`vzdump <vmid> --storage <storage>`) and reading
the log for the exclusion line, rather than just re-checking the config file — the log makes the
real behavior unambiguous: `excluding volume mount point mp0 ('/mnt/media') from backup
(disabled)` vs. it silently being included.

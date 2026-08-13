---
name: proxmox-zfs-root-mirror
description: This skill should be used when a Proxmox host's root pool (`rpool`) is a single ZFS disk with no redundancy and needs to become a mirror, or when an existing 2-drive ZFS root mirror needs to be grown to use more of each drive's capacity — all live, without reinstalling Proxmox or restoring guests from backup. Trigger phrases include "add redundancy to rpool", "mirror the boot drive", "zfs root mirror no reinstall", "grow zfs root partition live", "zpool attach boot disk", "expand rpool without downtime", "convert single disk zfs to mirror", "replace boot drive keep guests running".
version: 0.1.0
---

# Converting/growing a Proxmox ZFS root pool live, no reinstall

The instinct when someone wants to add disk redundancy to a Proxmox host is to assume it needs
a full reinstall + restore-every-guest-from-backup — especially if the host also runs its own
backup server as a guest (PBS-on-the-box-being-rebuilt is a real circular dependency). **Check
whether the root pool is already ZFS first** (`zpool status` — even a single-disk pool with no
redundancy is still a real zpool, just a single-device vdev). If it is, `zpool attach` converts
it to a live mirror in place — zero data risk, zero guest downtime beyond one confirmatory
reboot. Built and verified live 2026-08-13 on a Beelink Mini S13 (`pve`), going from a single
500GB SATA SSD to a full 1.82TB 2-way NVMe mirror, entirely without a reinstall.

## Step 1 — confirm the pool and boot setup

```bash
zpool status rpool          # single-vdev, no "mirror-N" line = no redundancy yet
zpool list                  # current SIZE/ALLOC/FREE
proxmox-boot-tool status    # confirms uefi vs grub, and which ESP UUIDs are synced
lsblk                       # confirm the new drive is present and genuinely blank
sgdisk -p /dev/sda          # note the existing partition layout (BIOS-boot / ESP / ZFS)
```

A stock Proxmox ZFS-root install has 3 GPT partitions: a small BIOS-boot stub (`EF02`), a
~1GB ESP (`EF00`), and the rest as the ZFS vdev (`BF01`). Confirm the new drive is truly empty
(`sgdisk -p /dev/nvmeXn1` shows no partitions) before touching anything.

## Step 2 — attach the new drive as a live mirror

```bash
sgdisk --replicate=/dev/nvme0n1 /dev/sda
sgdisk --randomize-guids /dev/nvme0n1
lsblk /dev/nvme0n1                          # confirm partitions 1/2/3 now exist

proxmox-boot-tool format /dev/nvme0n1p2 --force
proxmox-boot-tool init /dev/nvme0n1p2
proxmox-boot-tool status                    # both ESP UUIDs should now show "configured"

zpool attach rpool <existing-vdev-partition> /dev/nvme0n1p3
zpool status rpool                          # "resilver in progress"
```

**Gotcha:** `proxmox-boot-tool init` can fail immediately after `format` with `has wrong
filesystem (!= vfat)` — this is a stale `blkid` cache right after `mkfs.fat`, not a real
problem. Re-run `blkid /dev/nvme0n1p2` (forces a fresh read) then retry `init`; it succeeds.

**Gotcha:** `partprobe` is frequently not installed on Proxmox/Debian hosts — don't rely on it
being there.

Poll resilver progress (large pools can take a while — 272G took ~19 min on NVMe-vs-SATA in the
reference run, but the ETA is wildly pessimistic in the first ~30s and corrects sharply once
real throughput is sampled — don't react to an early "6 hours" estimate):

```bash
zpool status rpool | grep -E 'scan:|resilvered,'
```

Resilver completion looks like: `scan: resilvered 272G in 00:18:35 with 0 errors on ...`.

## Step 3 — confirmatory reboot

Prove the new drive is independently bootable before trusting it, rather than assuming the ESP
sync worked:

```bash
efibootmgr -v | head -20     # note BootCurrent and which partition GUID it maps to
reboot
# after it's back:
efibootmgr -v | grep BootCurrent
zpool status rpool           # still healthy, mirror intact across the reboot
findmnt /                    # still rpool/ROOT/pve-1
```

If `BootCurrent` maps to the *new* drive's ESP partition GUID, the firmware genuinely chose to
boot from it — strong confirmation, not just "it came back up."

**On a memory-tight host** (no swap, guests near the RAM ceiling): before rebooting, pause the
single largest/least-critical guest so Proxmox's boot sequence doesn't try to auto-start
everything simultaneously — `qm set <vmid> --onboot 0` *then* `qm stop <vmid>` (order matters;
stopping without disabling `onboot` first gets silently undone by the boot sequence). Restore
`--onboot 1` and `qm start` it back manually once the rest of the fleet is confirmed stable.

## Step 4 — replacing a drive (not just adding one)

If the goal is to swap an old drive out (not just add a new one alongside it — e.g. only 2
physical slots exist and both need to end up as the new drives):

```bash
zpool detach rpool <old-drive-partition>    # pool becomes single-vdev again, still healthy
# power off, physically swap the drive, power back on
proxmox-boot-tool status                    # will WARN the old ESP UUID "does not exist"
proxmox-boot-tool clean                     # expected cleanup step, not an error condition
```

Then repeat Step 2's attach procedure for the replacement drive.

## Step 5 — growing the mirror to use full drive capacity, live

If the new drive(s) are larger than the original (e.g. replacing a 500GB drive with 2TB
drives), the pool stays capped at the original partition size until you explicitly grow it.
This is a **live operation, no reboot required**, done one mirror leg at a time so redundancy
never actually drops:

```bash
sgdisk -d 3 -n 3:<original-start-sector>:0 -t 3:BF01 /dev/nvme0n1
partx -u /dev/nvme0n1                       # forces the kernel to notice the new partition
                                             # size WITHOUT a reboot -- use this instead of
                                             # partprobe, which is often not installed
zpool online -e rpool nvme0n1p3
zpool list                                  # SIZE unchanged -- expected, see below
```

Repeat for the second leg, then check again:

```bash
sgdisk -d 3 -n 3:<original-start-sector>:0 -t 3:BF01 /dev/nvme1n1
partx -u /dev/nvme1n1
zpool online -e rpool nvme1n1p3
zpool list                                  # SIZE now reflects the full capacity
```

**Mirror capacity = smallest member.** Growing only one leg's partition does nothing visible in
`zpool list` — the pool only actually expands once *every* mirror member has been grown. Don't
mistake the no-op after the first leg for a failure.

Use `-n 3:<start>:0` (not `-n 3:0:0`) to keep the exact original start sector — safer than
letting `sgdisk` pick a start, and guarantees no accidental shift of the partition's existing
data region. The end sector `0` means "use all remaining free space."

## Reference: full end-to-end timing from the verified run

- Initial mirror attach + resilver (272G): 18m35s, 0 errors.
- Drive-swap detach → replace → re-attach + resilver (271G): 6m06s, 0 errors (faster — likely
  less fragmentation/different read pattern on the fresh drive).
- Capacity grow (both legs, live, no resilver needed for this part): well under a minute of
  actual commands; `zpool online -e` takes effect immediately once both legs are resized.
- Post-completion `zpool scrub`: 269G, 5m57s, 0 errors, 0 repaired — worth running once
  everything's done as final verification, not just trusting "no errors during resilver."

Total real downtime across an entire single-disk → full-capacity 2-drive mirror conversion:
one confirmatory reboot + one power-off/power-on for the physical drive swap. No Proxmox
reinstall, no guest restore from backup, at any point.

---
name: proxmox-vm-igpu-passthrough
description: This skill should be used when passing an Intel iGPU (or other PCI device) through to a Proxmox VM via vfio-pci for hardware acceleration (transcoding, OpenVINO/ML inference, etc.) — as opposed to an LXC's simple device bind-mount. Covers checking IOMMU group isolation, host-side vfio-pci binding, the Terraform hostpci block, and guest-kernel-side gotchas (missing GPU drivers in cloud kernels, grub picking the wrong kernel, missing firmware). Trigger phrases include "vfio-pci passthrough", "IOMMU group", "pass GPU to proxmox VM", "hostpci vfio", "vainfo can't connect", "i915 declaring it wedged", "GuC firmware fetch failed", "cloud kernel missing i915", "grub boots wrong kernel same version", "intel_gpu_top", "OpenVINO GPU device", "linux-image-cloud-amd64 no gpu driver".
---

# Passing an Intel iGPU through to a Proxmox VM (vfio-pci)

Full host-to-guest procedure for exclusive PCI passthrough of an Intel iGPU to a Proxmox VM, so
a containerized app (Immich's `-openvino` ML image, Jellyfin-style VAAPI transcoding, etc.) can
use real hardware acceleration inside a VM rather than an LXC. First done 2026-07-18 passing an
Alder Lake-N iGPU to an Immich VM after decommissioning the Jellyfin LXC that previously used it
via simple device bind-mount. **This is a fundamentally different, heavier mechanism than LXC
GPU passthrough** — read the trade-off section first, it may not be the right call.

## Is this even the right call? (read before touching anything)

Unlike an LXC (which shares the host's kernel and can just bind-mount `/dev/dri`, letting the
host and every LXC use the GPU simultaneously), a VM has its own kernel and its own PCI space.
Getting a device into a VM means the **host physically detaches it** via `vfio-pci` and hands it
to exactly one VM. Check IOMMU group isolation first — if the GPU shares a group with unrelated
devices, this may not even be possible without ACS-override hacks:

```bash
lspci -nn | grep -i vga   # find the device, e.g. 00:02.0
for d in /sys/kernel/iommu_groups/*/devices/*; do
  n=${d#*/iommu_groups/}; n=${n%%/*}
  echo "Group $n: $(lspci -nns ${d##*/})"
done | grep -B2 -A2 -i vga
```

Also check for GVT-g/SR-IOV mediated-device support, which would let the GPU be *shared* across
multiple VMs instead of handed over exclusively:

```bash
ls /sys/class/mdev_bus/ 2>&1   # "No such file or directory" = no mdev/GVT-g support at all
```

If there's no mdev support (true for most consumer/low-power Intel iGPUs — confirmed on an
Alder Lake-N here), passthrough is **all-or-nothing**: the host and every other guest (including
any future LXC that might want the same GPU) lose access until this is reverted. Confirm this
trade-off explicitly before proceeding — it's exactly the kind of hard-to-undo, shared-resource
decision worth a formal plan (EnterPlanMode) and explicit sign-off, not something to do inline.

## 1. Host-side: enable IOMMU passthrough mode and bind vfio-pci

Check current kernel cmdline first — IOMMU can show as "active" in `dmesg` (DMAR/Translated
domain) even without the passthrough-mode flag explicitly set:

```bash
cat /proc/cmdline          # what's actually running
cat /etc/kernel/cmdline    # what's configured (systemd-boot; use /etc/default/grub for grub hosts)
```

Add `intel_iommu=on iommu=pt` to `/etc/kernel/cmdline`, then:

```bash
proxmox-boot-tool refresh
```

Bind `vfio-pci` to the device *before* the normal GPU driver (`i915`) can claim it, via a
`softdep`, not a blanket blacklist (which would break other Intel devices sharing the driver):

```
# /etc/modprobe.d/vfio.conf
options vfio-pci ids=<vendor>:<device>   # from `lspci -nn`, e.g. 8086:46d4
softdep i915 pre: vfio-pci
```

```
# /etc/modules-load.d/vfio.conf
vfio
vfio_iommu_type1
vfio_pci
```

```bash
update-initramfs -u -k all
```

**⚠️ Writing to `/etc/modprobe.d/` gets blocked by the Claude Code permission classifier** — same
family as the known `/etc/apt/apt.conf.d/*` block (persistent system-wide auto-run locations).
Don't fight it with workarounds; ask the user directly for permission or to place the file
themselves. Confirmed 2026-07-18: asking for permission and having the user grant it worked —
the retry then succeeded cleanly.

**Reboot the host.** This restarts every guest on it — flag the blast radius before doing it, not
just in the plan document. Verify after reboot:

```bash
lspci -k -s <bus:dev.fn>   # "Kernel driver in use: vfio-pci", not i915
```

### A reboot-wait gotcha: false "it's back up" positives

A naive "wait until ping/SSH succeeds again" loop can catch the host **mid-shutdown**, while
it's still briefly responsive before the actual restart — reporting "back up" seconds after the
reboot command was issued, when really nothing has rebooted yet. Confirmed exactly this
2026-07-18: a monitor reported `pve` back up ~15s after `reboot`, but `lspci` still showed the
old driver and `uptime` showed the *pre-reboot* uptime — the real shutdown hadn't happened yet.
**Wait for the host to become genuinely unreachable first, then wait for it to come back**, not
just "wait until reachable":

```bash
until ! ping -c1 -W1 <host-ip> >/dev/null 2>&1; do sleep 3; done   # confirm real shutdown
sleep 5
until ssh -o ConnectTimeout=3 <host> "systemctl is-system-running" 2>/dev/null | grep -qE "running|degraded"; do
  sleep 5
done
```

After any host-wide reboot, **verify every guest actually came back**, not just the one you
care about — `qm list`/`pct list` and check `onboot` is set on anything that should auto-start.
(Caught a real gap this way: Pi-hole, DNS-critical, was the only guest in the fleet without
`onboot=1` — invisible until it alone failed to restart.)

## 2. VM-side: attach the device

```bash
qm set <vmid> -machine q35              # recommended for PCIe passthrough reliability
qm set <vmid> -hostpci0 <bus>:<dev>.<fn>,pcie=1   # e.g. 00:02.0 -- NO domain prefix (not 0000:00:02.0)
qm reboot <vmid>                         # hostpci isn't hot-pluggable
```

See the `proxmox-terraform-provisioning` skill's Gotcha 12 for the Terraform `hostpci` block
syntax — unlike LXC `device_passthrough`, this works fine with a scoped API token.

## 3. Guest-side: the part an LXC never needs

This is the real difference from LXC passthrough. An LXC shares the **host's** kernel and
already-loaded firmware for free. A VM has its own independent kernel that has never seen this
GPU before and needs to be able to drive it from scratch.

### Gotcha: cloud-image kernels strip GPU drivers entirely

Debian's cloud kernel (`linux-image-cloud-amd64`, the default on most cloud-init VM images)
ships with `i915` (and other desktop/GPU drivers) removed — cloud VMs are assumed to never have
a real GPU. Confirmed via `modprobe i915` failing outright: `Module i915 not found`. Fix:

```bash
apt-get install -y linux-image-amd64   # the generic kernel, has i915
```

### Gotcha: grub may still boot the wrong (old) kernel

After installing the generic kernel, `GRUB_DEFAULT=0` / the simple top-level menu entry doesn't
reliably pick it over the old cloud kernel if both share an **identical version number** with
just a different flavor suffix (`6.12.95+deb13-cloud-amd64` vs `6.12.95+deb13-amd64`) — grub's
"latest kernel" heuristic can end up picking the wrong one, and a reboot silently comes back into
the same old kernel (`uname -r` still shows `-cloud-`). Don't fight the default — force a
one-time boot into the exact entry:

```bash
grep "menuentry '" /boot/grub/grub.cfg   # find the exact non-cloud menuentry_id_option string
grub-reboot 'gnulinux-advanced-<uuid>>gnulinux-<version>-amd64-advanced-<uuid>'
reboot
```

Confirm with `uname -r` after reboot, **then** remove the old kernel package entirely (dpkg
refuses to remove a *running* kernel, so this only works post-switch) — this also eliminates the
ambiguity for every future reboot, so it's worth doing rather than leaving both installed:

```bash
apt-get remove --purge -y linux-image-<old-version>-cloud-amd64 linux-image-cloud-amd64
```

### Gotcha: the driver binds but the GPU "declares itself wedged"

Even with the right kernel and `i915` bound (`lspci -k` shows it), the GPU can still be
non-functional. Check `dmesg`:

```
Failed to load DMC firmware i915/adlp_dmc.bin (-ENOENT)
firmware: failed to load i915/tgl_guc_70.bin (-2)
*ERROR* GT0: GuC initialization failed -ENOENT
*ERROR* GT0: Failed to initialize GPU, declaring it wedged!
```

Modern Intel iGPUs need proprietary GuC/DMC/HuC firmware blobs the kernel driver can't function
without. These live in Debian's `non-free-firmware` apt component (not enabled by default):

```bash
sed -i 's/^Components: main$/Components: main non-free-firmware/' /etc/apt/sources.list.d/debian.sources
apt-get update && apt-get install -y firmware-misc-nonfree
modprobe -r i915 && modprobe i915   # reload, no full reboot needed once firmware is on disk
dmesg | tail -15   # look for "Finished loading DMC firmware" / "GuC ... version" / "GUC: submission enabled"
```

## 4. Verify for real — three independent signals, not just "container started"

1. **`vainfo`** (needs `intel-media-va-driver` + `vainfo` packages) — confirms the userspace
   VAAPI driver actually initializes and lists real codec entrypoints. Headless guests need an
   explicit display target, plain `vainfo` tries X11 first and fails with `can't connect to X
   server` even when the device itself is fine:
   ```bash
   vainfo --display drm --device /dev/dri/renderD128
   ```
2. **`intel_gpu_top`** (`apt install intel-gpu-tools`) — the most conclusive check: shows live
   per-engine utilization (RCS = render/compute, what ML inference and transcoding both use).
   Real, non-zero, fluctuating `%` correlating with actual workload is definitive proof the GPU
   is doing work, not just present:
   ```bash
   intel_gpu_top -o -   # or interactive without -o
   ```
3. **The actual workload's own throughput**, before/after. Don't trust CPU% alone as a proxy —
   a container's CPU% can stay high even with GPU offload (pre/post-processing, marshalling,
   other concurrent work), so it's not proof of failure. For a job-queue-backed app, sample
   queue depth twice a fixed interval apart and confirm the trend flips from growing to
   shrinking — the same test that proved the bottleneck existed is what proves the fix worked.

## Gotcha: guest hangs completely on the first boot after a host reboot

Confirmed twice on an Alder Lake-N iGPU passed through to an Immich VM (2026-08-03, 2026-08-09):
after a `pve` host reboot, the *first* guest boot to touch the passed-through device can freeze
solid — not a slow service, the whole guest. Signature: `journalctl -b` shows a normal boot
reaching `Startup finished` (~8s), network/cloud-init complete fine, then the journal goes
completely silent (zero `docker.service`/downstream-service activity at all) shortly after a
stall in `systemd-timesyncd`. The VM stays "running" at the hypervisor level for as long as
you'll wait — no OOM kill, no panic, no crash logged anywhere. A second `qm stop`/`qm start` of
the *same* guest (no host reboot in between) reliably boots clean.

**Diagnose**: compare the hung boot against a clean one on the same guest:

```bash
journalctl --list-boots               # find the hung generation (its LAST ENTRY timestamp is
                                        # minutes/hours before the VM was actually stopped --
                                        # that gap between logged-until and stopped-at IS the hang)
journalctl -b -1 --no-pager | tail -80 # or whatever index the hung boot is
journalctl -b 0  --no-pager | grep -iE 'timesyncd|docker|Startup finished|i915|Cannot find any crtc'
```

Check the i915 driver messages in both — an upstream `WARNING: ... intel_bios_init` VBT-parsing
bug is common and **benign** on this hardware (appears identically on hung and clean boots, i915
recovers from it fine both times) — don't mistake it for the cause. Also check the host's own
kernel log for the same window; a real vfio-pci/reset/FLR problem would show there:

```bash
journalctl -k --since "<window start>" --until "<window end>" | grep -iE 'vfio|iommu|reset|FLR'
```

If the host log is silent too, the freeze is inside the guest's own first mediated-device
session — presumed to be a GuC/HuC firmware-load race that's more likely to manifest on a truly
cold device state (fresh host boot) than on a warm rebind. Not confirmable further without a
live crash capture (magic SysRq / NMI backtrace mid-hang, not attempted either time).

**Fix that actually worked both times**: don't wait for a generic "is it up yet" health check
with a long grace period — that just means minutes of avoidable downtime for a failure mode
that's already known to require exactly one bounce. Add a dedicated boot-triggered systemd
oneshot, ordered `After=... pve-guests.service`, that waits a short window (~3 min) after `pve`
itself boots, checks the guest's real online state (Tailscale peer status, not the QEMU guest
agent — the agent is itself one of the things that never starts during the hang), and
proactively bounces the guest once if still offline. Full implementation (Ansible playbook +
templates) in the homelab's `post-reboot-bounce.service` — see `project_boot_watchdog` memory.

## Reverting

```bash
qm set <vmid> -delete hostpci0
qm reboot <vmid>
# on the host: remove /etc/modprobe.d/vfio.conf, /etc/modules-load.d/vfio.conf,
# revert /etc/kernel/cmdline, then:
proxmox-boot-tool refresh && update-initramfs -u -k all
reboot
```

GPU returns to host-only, available for a future LXC (simple bind-mount, no vfio-pci needed —
see the `jellyfin-proxmox-deployment` skill) or a different VM.

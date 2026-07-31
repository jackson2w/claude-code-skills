---
name: proxmox-vm-crash-diagnosis
description: This skill should be used when a Proxmox VM shows `status: stopped` with no corresponding shutdown task in its history, when a VM restarts but becomes unresponsive (no SSH, no ping, or `qm status` says running but nothing actually answers), when deciding whether a slow-booting VM is genuinely still booting or actually hung, or when a Proxmox host has run out of memory and the OOM killer terminated a qemu process. Trigger phrases include "vm stopped unexpectedly", "oom killer killed vm", "qm status stopped no shutdown task", "vm hung after restart", "no ssh after qm start", "vm not responding after boot", "proxmox out of memory", "kvm process killed oom", "vm won't come back up", "is this vm actually stuck or just slow", "qm terminal tcgetattr inappropriate ioctl".
version: 0.1.0
---

# Diagnosing and recovering a crashed or hung Proxmox VM

Covers two related but distinct problems: figuring out *why* a VM went down (often an OOM
kill, not a clean shutdown), and figuring out whether a VM that came back up but isn't
responding is genuinely stuck or just slow — before deciding whether to force-restart it again.
Built and verified live 2026-07-31 recovering Immich's VM (145) after `pve`'s first real OOM
kill: two restart attempts were needed, the first hung completely, and distinguishing "hung"
from "still booting" mid-incident (rather than guessing) is the actual point of this skill.

## Step 1 — confirm whether it was a clean shutdown or a crash

`qm status <vmid>` showing `stopped` doesn't say *why*. Check the node's own task log for a
matching shutdown task before assuming anything:

```bash
pvesh get /nodes/<node>/tasks --limit 20 --output-format json | \
  jq -r '.[] | "\(.starttime) \(.id) \(.type) \(.status // "running")"' | sort -rn
```

A clean shutdown/reboot shows a `qmshutdown` (or `qmreboot`) task immediately before the
`stopped` state, at the expected time. **No such task at all is the signature of a crash**, not
a clean stop — check the host's kernel log next:

```bash
journalctl --since '<window>' --until now -k | grep -iE 'oom|killed process|panic|error'
```

An OOM kill looks like this (the process being sacrificed, its cgroup, and the trigger are all
named directly):

```
kernel: oom-kill:constraint=CONSTRAINT_NONE,...,task_memcg=/qemu.slice/<vmid>.scope,task=kvm,pid=<pid>,uid=0
kernel: Out of memory: Killed process <pid> (kvm) total-vm:<X>kB, anon-rss:<Y>kB, ...
```

The `task_memcg=/qemu.slice/<vmid>.scope` line identifies exactly which VM was sacrificed even
when several guests are running on the same host.

## Step 2 — check memory headroom before restarting anything

If it was an OOM kill, restarting immediately without checking free memory risks an instant
repeat. Check both host-level and guest-level:

```bash
free -h   # on the Proxmox host -- read "available", not just "free"
```

**Host-side qemu process RSS is not a reliable proxy for real in-guest memory demand.**
`virtio-balloon`'s `free-page-reporting` releases unused guest pages back to the host
asynchronously, not instantly — a qemu process can show host-side RSS near its full configured
allocation even when the guest itself is barely using any of it. Check inside the guest too,
once it's back up, before concluding the VM itself "needs" all of its allocated memory:

```bash
free -h                                                             # inside the guest
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}'  # if Docker-based
```

If steady-state host `free -h` "available" stays persistently low even once everything is
running normally (not just during a transient boot/warm-up spike — recheck after a minute or
two to tell the difference), that's a real capacity signal, not noise. Don't restart more
guests or apply other memory-hungry changes (a host-level reboot for a kernel/hypervisor update,
e.g.) until it's resolved or a human explicitly accepts the risk.

## Step 3 — restart, then verify it's actually booting, not just "running"

```bash
qm start <vmid>
```

`qm status <vmid>` reporting `running` only means the qemu process exists — it says nothing
about whether the guest OS inside is making progress. A VM can sit in this state indefinitely
while genuinely hung. Don't assume a slow boot is "just slow" — measure it:

```bash
# Sample real CPU ticks (not the lifetime-average % from `ps`) a few seconds apart:
pid=$(cat /var/run/qemu-server/<vmid>.pid)
cat /proc/$pid/stat | awk '{print $14, $15}'   # utime stime
sleep 10
cat /proc/$pid/stat | awk '{print $14, $15}'   # utime stime again
```

Ticks climbing meaningfully between samples (tens to hundreds over ~10s) means the guest is
genuinely doing boot work — kernel decompression, systemd unit startup, container image
extraction, etc. **Ticks essentially flat (single-digit deltas) after more than a couple of
minutes is the signature of a genuinely stuck boot**, not a slow one — a normal boot with
several services (Docker containers, ML model loading, etc.) shows real, sustained CPU
consumption throughout; a hang shows near-zero.

Corroborate before concluding it's stuck: `ping -c2 <guest-ip>` working (kernel/network stack
up) while `nc -zv <guest-ip> 22` refuses (nothing listening on SSH yet) is consistent with
*either* a slow-but-real boot or an early hang — the CPU-tick test above is what actually
distinguishes them, don't rely on ping/port-refusal alone.

### Attempting console access (limited from a non-interactive shell)

`qm terminal <vmid>` needs a real TTY — running it over a plain non-interactive SSH/Bash
invocation fails immediately with `tcgetattr: Inappropriate ioctl for device` rather than
showing anything useful. Wrapping in `script` can sometimes fake a pty (`script -qc "qm
terminal <vmid>" /dev/null`), but this is unreliable from a tool-driven (non-terminal) session —
don't spend long fighting it. `qm sendkey <vmid> ret` is worth trying once (in case the guest is
stuck at an interactive boot-menu prompt waiting for a keypress) but isn't a substitute for the
CPU-tick test above, and won't unstick a genuine kernel/init hang.

## Step 4 — if genuinely stuck, force-stop and restart clean, don't just wait longer

```bash
qm stop <vmid>     # hard stop, appropriate for a VM already confirmed unresponsive
qm start <vmid>
```

Re-run the CPU-tick sampling from Step 3 on the new boot attempt. Confirmed live: a first
restart attempt hung completely (flat CPU, no SSH, for 12+ minutes) while the very next
`qm stop`/`qm start` cycle booted clean in about a minute, all services healthy — the hang was
a one-off boot-path fluke, not a persistent problem with the VM's config or disk. A **second**
hang in a row would point toward something deeper (corrupted filesystem, an incompatible
device/passthrough state) worth escalating rather than repeating the same cycle indefinitely.

## Step 5 — verify full recovery, not just "it's pingable again"

Reachability alone isn't proof the actual workload is healthy. Check the real service:

```bash
docker compose ps --format 'table {{.Name}}\t{{.Status}}'   # every container healthy, not just "Up"
curl -s <internal health/version endpoint>                   # the app itself responds correctly
```

And confirm externally too (Tailscale Serve URL, LAN reachability — whatever the real access
path is), not just from the Proxmox host or over a direct SSH session to the guest itself.

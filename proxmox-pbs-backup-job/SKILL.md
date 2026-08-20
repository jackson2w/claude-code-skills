---
name: proxmox-pbs-backup-job
description: This skill should be used when adding a new host (LXC or VM) to an existing Proxmox Backup Server nightly backup schedule, creating a vzdump job via `pvesh`, debugging a backup job that succeeds but the prune step fails with a permission error, or excluding one specific mount point (e.g. a bulky media/data volume) from an LXC's backup while still backing up its rootfs. Trigger phrases include "add backup job pvesh", "vzdump schedule new host", "pbs prune permission denied", "Datastore.Modify Datastore.Prune missing", "backup job finished with errors", "proxmox-backup-client prune permission check failed", "exclude mount point from backup", "mp0 backup=0", "vzdump exclude volume".
---

# Adding a host to an existing PBS nightly backup schedule

Use this when a new LXC/VM needs to join an existing Proxmox Backup Server datastore's nightly
backup rotation (as opposed to setting up PBS or a datastore from scratch — that's a bigger,
one-time task). Verified end-to-end adding the Homepage dashboard (VMID 140) to an existing
`pihole-and-friends` datastore already backing up Pi-hole and Home Assistant.

## Create the job via `pvesh`, not by hand-editing `/etc/pve/jobs.cfg`

`pvesh` is available directly on the Proxmox host (`pve`) even though it isn't installed on the
PBS host itself — backup jobs are configured cluster-side (`/etc/pve/jobs.cfg`), not on PBS.
Match whatever schedule offset and retention the existing jobs already use rather than
inventing new values:

```bash
# Check what's already scheduled first, so the new job doesn't collide:
pvesh get /cluster/backup --output-format json

pvesh create /cluster/backup \
  --vmid <new-vmid> \
  --storage <existing-pbs-storage-name> \
  --mode snapshot \
  --schedule 'sun..sat HH:MM' \
  --enabled 1 \
  --comment '<Host> nightly backup to PBS' \
  --prune-backups keep-daily=7,keep-weekly=4
```

Stagger the schedule time a few minutes after the last existing job in the same datastore (e.g.
`03:00`, `03:15`, `03:20`) rather than running them concurrently.

## Always manually trigger the new job once — don't just wait for the cron schedule

A scheduled job succeeding tonight doesn't confirm the *prune* step works (see the gotcha below;
prune can fail silently in a way that only shows up in the task log, not as a missing backup).
Trigger it for real and read the full output:

```bash
vzdump <vmid> --storage <storage> --mode snapshot --prune-backups keep-daily=7,keep-weekly=4
```

Look for `Backup job finished successfully` at the end, not just `Duration: ...` after the
upload — a failed prune still uploads the backup fine and only fails on the line after.

## Gotcha — the backup service account can lack `Datastore.Prune`, and this fails silently per-job, not fleet-wide

A PBS service account scoped with only `DatastoreReader` + `DatastoreBackup` (a reasonable-looking
least-privilege choice) can successfully upload backups indefinitely while **every prune step
fails**:

```
ERROR: prune 'ct/<vmid>': proxmox-backup-client failed: Error: permission check failed - missing Datastore.Modify|Datastore.Prune on /datastore/<name>
INFO: Backup job finished with errors
```

This is easy to miss because the backup itself (the part anyone actually checks — "did last
night's backup run?") succeeds every time; only the prune line fails, silently accumulating
backups past the configured retention. **This is a shared-account permission, so if it's missing
it's missing for every job on that datastore, not just the new one** — check by manually
triggering an *existing* job (e.g. the oldest one) after the fix, not just the new one, to
confirm the fix actually resolved a fleet-wide gap rather than something scoped to the new host.

Fix: grant `DatastorePowerUser` (read + backup + prune + verify — the PBS role designed
specifically for an automated backup account that also manages its own retention) on the
datastore path:

```bash
proxmox-backup-manager acl update /datastore/<name> DatastorePowerUser --auth-id <backup-user>@pbs
```

`acl update` is additive — it doesn't need the old narrower roles removed first, though they
become redundant once `DatastorePowerUser` is in place.

**This is a permission escalation on a shared credential, not a scoped fix for one job** — it
affects every existing backup job using that account. Flag it and get explicit confirmation
before applying, don't fix it silently as a side effect of an unrelated task.

## Excluding one mount point from backup (e.g. a bulky media/data volume)

A container with a separate large data mount (media library, scratch data, anything bulky and
reproducible from elsewhere) usually shouldn't have that volume backed up nightly alongside the
small rootfs — it wastes datastore space backing up content that isn't actually irreplaceable.
Proxmox supports this per-mount-point, not just per-container:

```bash
pct set <vmid> -mp0 local-zfs:subvol-<vmid>-disk-1,mp=/mnt/media,size=500G,backup=0
```

Proxmox's default for a *volume* mount point (as opposed to a bind-mount of an existing host
directory) is backed-up-by-default when the `backup` flag is absent — you have to set
`backup=0` explicitly to exclude it. If provisioning this container via Terraform's
`bpg/proxmox` provider, **don't trust `mount_point.backup = false` in the `.tf` config alone** —
see that skill's Gotcha 11: the attribute can be recorded in Terraform state without the real
`backup=0` flag landing in `/etc/pve/lxc/<vmid>.conf`. Always verify directly:

```bash
grep ^mp0 /etc/pve/lxc/<vmid>.conf   # must show `,backup=0` explicitly
```

Confirm the exclusion actually works by triggering a real backup and reading the log, not just
the config file — the log line makes it unambiguous:

```
INFO: including mount point rootfs ('/') in backup
INFO: excluding volume mount point mp0 ('/mnt/media') from backup (disabled)
```

If a mount point isn't irreplaceable (e.g. it holds the only copy of something), don't exclude it
from backup without a separate backup plan for that content — flag this explicitly rather than
silently trading data safety for datastore space.

## A datastore needs a `gc-schedule` set explicitly — it is not on by default

Creating a PBS datastore (`proxmox-backup-manager datastore create`) does **not** set up
automatic garbage collection. Per-job `--prune-backups` only updates snapshot *metadata*
(marks old snapshots for removal per retention) — it does not reclaim the underlying chunk-store
disk space. Without a scheduled GC, deleted/superseded chunks accumulate forever and the
datastore can silently fill to 100%, causing every subsequent backup job to fail with `No space
left on device`, even though retention/pruning has been "working" the whole time. Check with:

```bash
proxmox-backup-manager datastore show <name>   # look for a gc-schedule row; if absent, none is set
```

Fix — set one at datastore creation time, not as an afterthought:

```bash
proxmox-backup-manager datastore update <name> --gc-schedule 'sun 04:00'
```

**GC is two-phase and won't reclaim space on its first run after a big deletion.** Phase 1 marks
chunks referenced by *current* backup indices; phase 2 sweeps everything else, but only actually
deletes chunks whose access-time is *older* than a safety cutoff (default ~1 day + 5 min) — chunks
touched more recently are left as "pending removal" to avoid racing a backup that's still
mid-upload. A GC run right after deleting several groups can report `Removed garbage: 0 B` while
also reporting `Pending removals: NN GiB` — this is expected, not a bug; a second GC run once the
cutoff clears (usually within ~24h of the chunks' last real use) actually frees the space. Don't
assume GC "didn't work" from a 0 B removal on the first pass — check `Pending removals` in the
output.

## Monitor datastore disk usage — a full datastore fails every job at once with no advance warning

Nothing about `pvesh get /cluster/backup` or a single job's own history surfaces that the
*datastore itself* is nearly full — every guest's job just starts failing with `No space left on
device` the night it tips over 100%, with no warning the nights before. If a nightly/weekly
backup-status check doesn't already cover this, add a `df -h <datastore-path>` (or the PBS API's
datastore status endpoint) threshold check (e.g. warn at 80%, fail at 90%) — this is the single
highest-leverage check for catching the failure mode below before it happens, rather than
diagnosing it after the fact. Hit this for real 2026-07-19: `pihole-and-friends` hit 100% used
(93GB/98GB) overnight, failing Homepage/n8n/Immich's jobs simultaneously; root cause was two
compounding gaps — no `gc-schedule` (above) plus stale backups for four services decommissioned
days earlier never pruned (see next section) — neither of which any monitoring caught until
backups actually started failing. The homelab project's nightly backup summary
(`backup-status-checks.sh`) now implements exactly this check (added same day) — use it as a
reference implementation (a plain `df --output=pcent`/`--output=avail` SSH call, two thresholds,
feeding into the same overall-status/follow-up-prompt machinery as its per-job checks) rather
than reinventing the shape for a new project.

## When decommissioning a guest, its PBS backups don't disappear with it — decide on them explicitly

Destroying a VM/LXC via Terraform/`pct destroy`/`qm destroy` does **not** touch its existing PBS
backups — they sit in the datastore under their own group (`ct/<vmid>` or `vm/<vmid>`) consuming
real disk space indefinitely, since nothing is left to trigger their retention-based pruning
(that only happens as a side effect of a *new* backup running via `--prune-backups`, which will
never happen again for a destroyed guest). "Let them age out naturally per retention" is not
actually true for a decommissioned guest — there is no more pruning happening, so they simply sit
there consuming datastore capacity forever unless removed explicitly. Delete a decommissioned
guest's backup group via the PBS API (no CLI subcommand exists for this as of this writing):

```bash
# from the PBS host itself, using a scoped API token (create one, grant DatastoreAdmin
# on /datastore/<name>, delete both when done — see below)
curl -sk -X DELETE \
  -H "Authorization: PBSAPIToken=<tokenid>:<secret>" \
  "https://localhost:8007/api2/json/admin/datastore/<name>/groups?backup-type=<ct|vm>&backup-id=<vmid>"
# response: {"data":{"protected-snapshots":0,"removed-groups":1,"removed-snapshots":N}}
```

If you don't already have a token scoped for datastore admin, mint a short-lived one and delete
it again afterward rather than widening a long-lived credential's scope:

```bash
proxmox-backup-manager user generate-token root@pam housekeeping-tmp --comment '<why, and expected deletion>'
proxmox-backup-manager acl update /datastore/<name> DatastoreAdmin --auth-id 'root@pam!housekeeping-tmp'
# ... do the deletes ...
proxmox-backup-manager acl update /datastore/<name> DatastoreAdmin --auth-id 'root@pam!housekeeping-tmp' --delete
proxmox-backup-manager user delete-token root@pam housekeeping-tmp
```

This is a real, deliberate decision point, not a formality — add "prune PBS backups for the
decommissioned guest (or explicitly note you're keeping them and for how long)" to whatever
decommission checklist you're following, alongside the already-standard Prometheus/Homepage/
Pi-hole-DNS/Tailscale-device cleanup steps. Run GC (above) afterward to actually reclaim the
freed chunks.

**Checking whether a group exists at all doesn't need a token.** Before minting a temp
DatastoreAdmin token just to *check*, it's simpler to look at the datastore's own directory
layout directly (root SSH to the PBS host is enough — no API, no token):

```bash
ssh pbs "find /<datastore-path>/vm /<datastore-path>/ct -maxdepth 1 -mindepth 1 -type d"
# e.g. /mnt/pbs-datastore/vm/145, /mnt/pbs-datastore/ct/101 -- the trailing number is the vmid
```

Each backup group is just a `vm/<vmid>` or `ct/<vmid>` directory — `grep` the output for the
vmid you care about. Reserve the token-minting dance above for the actual delete, once you've
confirmed via this read-only check that there's something to delete. Used this in
`homelab-ansible/scripts/decommission-touchpoint-check.sh` (see the homelab's
`project_ansible_graduation_catalog` memory) — also where a variable named `GROUPS` turned out
to silently misbehave (it's a bash built-in special variable, an array of the process's Unix
groups); name it something else.

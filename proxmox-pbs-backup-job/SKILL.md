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

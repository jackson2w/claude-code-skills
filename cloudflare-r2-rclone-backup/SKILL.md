---
name: cloudflare-r2-rclone-backup
description: This skill should be used when setting up a nightly/periodic offsite backup of a directory or archive (Proxmox Backup Server datastore, database dumps, photo libraries, any local directory) to a Cloudflare R2 bucket via rclone's S3-compatible API — or when debugging an existing rclone-to-R2 sync job. Trigger phrases include "offsite backup to R2", "rclone sync to Cloudflare", "back up to R2", "R2 rclone", "unknown flag: --delete" (rclone), "Can't set -v and --log-level", "501 NotImplemented" from an S3/R2 sync, or "create R2 access key".
---

# Cloudflare R2 + rclone offsite backups

Use rclone to mirror a local directory (backup archive, datastore, photo library, anything) to a
Cloudflare R2 bucket on a schedule. This is a **host-side** pattern — the sync runs as a systemd
timer on the machine that already has the data, not as a Cloudflare Worker. Workers have
per-invocation subrequest/CPU-time limits that make them a poor fit for pushing GBs of binary data
through; R2's role here is just the storage destination + a scoped credential, not compute.

## 1. Create the bucket and a scoped credential

- **Bucket**: create via the Cloudflare dashboard, `wrangler`, or an R2-bucket-creation MCP/API
  tool if one is available. Pick a bucket name distinct from any existing buckets in the account
  (don't collide with an unrelated bucket's namespace).
- **R2 access key (S3-compatible Access Key ID + Secret Access Key)**: this is **not** the same
  thing as a normal Cloudflare API token, and a normal Cloudflare API token scoped to
  R2/KV/Pages *object* operations generally **cannot mint one** — that requires the separate,
  more sensitive "API Tokens Edit" permission. Don't broaden an existing automation token's
  scope just to bootstrap this. Instead, create it via the dashboard: **R2 → Manage API Tokens
  → Create API token**, scoped to:
  - Permission: **Object Read & Write** (not Admin Read & Write — that's for bucket-level ops
    like CORS/lifecycle rules, which this job doesn't need).
  - Specify bucket: the one bucket this job targets, not "Apply to all buckets."
  - Copy the three values it shows **once**: Access Key ID, Secret Access Key, and the S3
    endpoint (`https://<account-id>.r2.cloudflarestorage.com`).
- Store these three values in a root-owned, mode-`600` env file on whatever host runs the sync
  (or on the Ansible controller if deploying via Ansible — see §4). Never commit them, never put
  them in `--extra-vars` on a CLI (shell history exposure).

## 2. Configure rclone via environment variables (no rclone.conf needed)

rclone supports configuring a remote purely through env vars, which avoids ever writing an
`rclone.conf` file containing secrets:

```
RCLONE_CONFIG_R2_TYPE=s3
RCLONE_CONFIG_R2_PROVIDER=Cloudflare
RCLONE_CONFIG_R2_ACCESS_KEY_ID=<access key id>
RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=<secret access key>
RCLONE_CONFIG_R2_ENDPOINT=<https://account-id.r2.cloudflarestorage.com>
RCLONE_CONFIG_R2_ACL=private
```

This defines a remote named `R2` (rclone lowercases the env var segment to the remote name), so
commands reference it as `r2:bucket-name`.

## 3. The rclone command — three real flag gotchas

The correct sync command:

```bash
rclone sync "${SOURCE_DIR}" "r2:${BUCKET}" --checksum --no-update-modtime --log-file="${LOG_FILE}" --log-level INFO
```

Gotchas that will bite on the first run if not accounted for:

- **`--delete` is not a valid flag for `rclone sync`** — it's a hard error (`unknown flag`), not
  a no-op. `sync` already deletes destination files absent from source *by default*; `--delete`
  (as `--delete-before/-during/-after`) is a `copy`/`move`-only option for opting *into* deletion
  there. If migrating a command from `copy` to `sync`, drop this flag.
- **`-v` and `--log-level` are mutually exclusive** (`Can't set -v and --log-level`). Use
  `--log-level INFO` (or `DEBUG`) alone when a `--log-file` is already being written to.
- **R2 returns `501 NotImplemented` when rclone tries to fix up an object's modification time
  after transfer via a self-copy** (a metadata-only `CopyObject` to the same key) — R2's S3
  implementation doesn't support that call. Symptom: the sync log shows dozens/hundreds of
  `Failed to copy: NotImplemented` errors on files whose *content* transferred fine, then
  rclone's built-in retry logic (`Attempt 2/3 succeeded`) quietly papers over it into an eventual
  exit 0 — easy to miss since the job technically "succeeds," just noisily and with wasted
  retries on every single run. Fix: add `--no-update-modtime` (skips the modtime-fixup call
  entirely) and `--checksum` (compares files by hash instead of size+modtime, sidestepping the
  need for accurate remote modtimes at all — also just a better comparison strategy when the
  source data is content-addressed, e.g. backup chunk files named by their own hash).

## 4. Wiring: systemd oneshot + timer (Ansible-managed example)

Pattern used successfully for a Proxmox Backup Server → R2 job:

- A bash wrapper script (`/opt/<job>/sync.sh`) runs the rclone command, checks the exit code,
  and sends a short success notification or a failure notification with a log tail (see §5).
- A systemd **oneshot service** (`EnvironmentFile=` pointing at the root-owned 600 env file,
  `ExecStart=` the wrapper script) plus a **timer** (`OnCalendar=`) scheduled to run comfortably
  after any upstream job the source data depends on (e.g. 30 min after a nightly backup job
  finishes, not immediately after/concurrent with it).
- If deploying via Ansible from a separate controller host: read the R2 credential file with
  `lookup('file', '/path/on/controller')` in playbook vars (this runs on the controller, not the
  managed host) and extract individual values with `regex_findall('KEY=(.*)')` rather than trying
  to build a dict from parsed pairs — Jinja's `dict()` global is Python's real `dict()` and does
  accept an iterable of pairs, but per-key `regex_findall` extraction is simpler to read and
  debug than constructing an intermediate list-of-tuples.
- Remember to explicitly create the destination config directory (e.g. `/root/.config`) before
  writing the env file into it — a fresh minimal host image may not have it yet, and `copy`
  fails with "Destination directory does not exist" rather than creating it implicitly.

## 5. Verify for real, not just "the job exited 0"

A clean exit code is not proof of a working backup. Prove it:

- **Pull a file back down** (`rclone copyto r2:bucket/path /tmp/check`) and diff/checksum
  (`sha256sum`) it against the source file — confirms round-trip integrity, not just that
  upload requests didn't error.
- **Actually trigger a test notification** and check the provider's API response (e.g.
  Telegram's `sendMessage` returning `{"ok":true,"result":{"message_id":...}}`) rather than just
  trusting a `curl` exit code of 0, which only proves the HTTP request completed, not that the
  message was accepted/delivered.

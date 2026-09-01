---
name: cloudflare-r2-restic-backup
description: This skill should be used when setting up a nightly/periodic encrypted backup of a directory (an app's state/data dir, a database dump, an agent's working directory) to a Cloudflare R2 bucket via restic, or when debugging an existing restic-to-R2 systemd timer job. Distinct from the `cloudflare-r2-rclone-backup` skill — that one covers plain `rclone sync` (mirrors a tree as-is, no encryption/dedup/snapshots); this one covers `restic` (client-side encrypted, deduplicated, snapshotted, with retention/pruning) — pick restic whenever the source is app state you'd want point-in-time recovery of, not just an already-static archive worth mirroring. Trigger phrases include "restic backup to R2", "restic R2 repository", "nightly restic backup", "restic systemd timer", "restic keep-daily keep-weekly prune", "restic init repository", "restic check integrity", "restic restore verify", "restic unable to open cache", "R2 access key for restic", "AWS_ACCESS_KEY_ID restic env", "credential assert guard rail ansible", "restic backup credential not yet populated".
---

# Restic backups to Cloudflare R2

Built and verified twice with an identical shape: `dfw` (Vultr VPS, OpenClaw workspace +
Vaultwarden + WordPress, 2026-08-16) and `hermes-agent` (Vultr VPS, Hermes gateway state,
2026-09-01). Second build took under an hour end-to-end including a real restore verification —
this skill exists so a third doesn't have to re-derive any of it.

## When restic, not rclone

`cloudflare-r2-rclone-backup` (sibling skill) mirrors a directory tree as-is — right for content
that's already static and just needs an offsite copy (a media library, exported archives). This
skill is for **application state you want point-in-time recovery of** — config, databases,
session/history stores, anything that changes daily and where "last night's version" matters,
not just "a copy exists somewhere." Restic adds client-side encryption, deduplication across
snapshots, and a real retention policy (`forget --prune`) that rclone sync doesn't have.

## The reusable shape

One `systemd` oneshot service + timer pair, one wrapper script, one Ansible playbook. Deploy
per-host under `/opt/<name>-backup/backup.sh` (root:root, mode 0700).

### Wrapper script skeleton

```bash
#!/bin/bash
set -uo pipefail
LOG_FILE=/var/log/<name>-backup.log
BACKUP_PATH=/path/to/state/dir

set -a
source /root/.config/telegram-bot.env        # shared fleet alert bot, not the app's own bot
source /root/.config/<name>-restic-r2.env    # RESTIC_PASSWORD, RESTIC_REPOSITORY, AWS_*
set +a

exec >>"$LOG_FILE" 2>&1
echo "=== backup run: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="

# Idempotent init -- only the FIRST run on a fresh bucket takes this branch.
if ! restic snapshots >/dev/null 2>&1; then
  restic init || { send_telegram_failure "... backup failed" "repo init failed"; exit 1; }
fi

restic backup "$BACKUP_PATH" --exclude=... || { send_telegram_failure ... ; exit 1; }
restic forget --keep-daily 7 --keep-weekly 4 --prune || { send_telegram_failure ... ; exit 1; }
restic check || { send_telegram_failure ... ; exit 1; }

send_telegram "✅ ... backup ok. $(restic snapshots --json | grep -o '\"id\"' | wc -l) snapshot(s) retained."
```

`send_telegram`/`send_telegram_failure`/`html_escape` can be inline in the script (a handful of
lines — see either live implementation) or pulled from a shared lib if the host already has one
for other reports; don't add a shared-lib dependency to a single-purpose backup script on a host
that doesn't already have one for something else.

**Exclude reproducible/ephemeral subdirectories explicitly** — caches, venvs/`node_modules`
equivalents, exec sandboxes, anything regenerable on `apt install`/`npm install`. Backing these
up wastes R2 storage and slows every run for zero recovery value. List them by name rather than
a generic size/mtime heuristic — explicit is auditable, a heuristic silently drifts.

### Systemd unit pair

Oneshot service (`ExecStart=<backup_dir>/backup.sh`), separate timer
(`OnCalendar=*-*-* HH:MM:00 UTC`, `Persistent=true`). Keep the two files separate rather than
`ExecStartPre`-chaining anything into one unit — a plain oneshot is easier to trigger manually
for testing (`systemctl start <name>-backup.service`) without waiting for the timer.

**Retention default across both live implementations**: `--keep-daily 7 --keep-weekly 4
--prune`. Treat this as the fleet baseline, not a hard rule — widen it for data that changes
rarely or narrow it for a bucket with real storage-cost pressure.

## The Ansible playbook pattern

The one design choice worth carrying forward deliberately: **assert the credential file exists
and fail loudly before deploying anything**, rather than deploying a timer that will silently
fail its first real run at 3am.

```yaml
- name: Assert credential files exist with the expected permissions
  ansible.builtin.stat:
    path: "{{ item }}"
  register: cred_file_stat
  loop:
    - /root/.config/telegram-bot.env
    - /root/.config/<name>-restic-r2.env

- name: Fail if a required credential file is missing
  ansible.builtin.assert:
    that: item.stat.exists
    fail_msg: "{{ item.item }} is missing -- populate it out-of-band before this playbook can be trusted."
  loop: "{{ cred_file_stat.results }}"
  loop_control:
    label: "{{ item.item }}"
```

Credentials are **never templated by the playbook itself** — they're populated out-of-band
(the human writes the file directly, or it's copied from another host's already-live copy via a
single piped `ssh ... | ssh ...` that never prints the value — see the credential-rotation-
protocol skill). The playbook's job is to verify the file is there with the right permissions,
deploy everything downstream of it, and refuse cleanly if it isn't yet. Verify this guard rail
actually works by running the playbook once *before* the credential file exists — it should fail
on the assert task with a clear message, not deploy a half-working timer.

Deploy the script with `validate: 'bash -n %s'` on the `copy` task — catches a syntax error at
apply time instead of at 3am.

## Provisioning the R2 side

1. **Create the bucket.** A plain per-project Cloudflare API token may not have R2 permission
   even if an old note claims it does — R2 permissions have drifted out from under
   general-purpose deploy tokens on more than one occasion. If a token 403s on
   `GET/POST /accounts/{id}/r2/buckets` with error 10000, don't assume R2 needs a whole new
   token: a connected Cloudflare Developer Platform MCP integration (if available in the
   environment) typically carries independent R2 bucket permissions and can create/list/delete
   buckets directly, even when the plain API token can't.
2. **Mint the S3-compatible access key.** This step has no API path at all, regardless of any
   token's scope — R2 access keys (Access Key ID/Secret) are dashboard-only:
   dash.cloudflare.com → R2 → Manage API Tokens → scope to the one bucket, Object Read & Write.
   This is always a human action.
3. **Repository URL**: `s3:https://<account_id>.r2.cloudflarestorage.com/<bucket-name>`.
4. **`RESTIC_PASSWORD`** is a separate, local repository-encryption passphrase — not an R2
   credential at all. Pick a strong one and save it somewhere durable (password manager) before
   the first `restic init` runs; **there is no recovery path if it's lost**, the data becomes
   permanently unreadable even though the encrypted blobs still exist in the bucket.

Hand the credential-file contents to the human to write directly via their own SSH session
(never relay a live secret value through a chat message) — same discipline as every other
credential in this environment.

## Should this credential go through a credential broker (e.g. Agent Vault)?

No, if the consuming process is a fixed, non-agentic script (a cron/systemd job) rather than an
LLM-driven agent process. A broker like Agent Vault protects credentials an *agent* holds and
calls out with during its own reasoning — the threat model is a compromised/prompt-injected
agent misusing its own key. A backup script has no adversarial input surface to protect against;
it's deterministic automation, same category as the R2 credential itself. It's also
**structurally incompatible** with the typical broker mechanism (a MITM proxy injecting a value
into outbound HTTPS calls): restic computes an AWS SigV4 signature from the real secret *before*
the request leaves the host, so the secret must already be in restic's hands regardless, and
`RESTIC_PASSWORD` is a local encryption passphrase with no network call to intercept at all. Keep
these credentials in a plain root-owned, mode-600 `.env` file.

## Verification discipline — don't call it done on a clean `ansible-playbook` run

A playbook reporting `changed` for every task proves the files were written, not that a backup
will actually work at 3am. Every build should finish with:

1. Manually trigger the oneshot service (`systemctl start <name>-backup.service`) rather than
   waiting for the timer — confirms the whole path works before the human goes to sleep on it.
2. Tail the log for a clean run: file/dir counts, `restic check` reporting "no errors were
   found", and the Telegram success message actually landing.
3. **Restore into a scratch directory and diff/cmp at least one file against the live source**
   (`restic restore latest --target /tmp/<x>-restore-test`, then `diff`/`cmp` a config file and
   any binary state file). A backup that was never restored is a hypothesis, not a backup.
   Delete the scratch directory afterward.

Skipping step 3 is the most common way a "verified" backup turns out to be unusable months
later — a clean `restic backup`/`check` exit code proves the data was written and is internally
consistent, not that it decrypts back into the original bytes with the credentials actually on
file.

## Known cosmetic gap (present in both live implementations, not yet fixed)

Neither systemd unit sets `Environment=HOME=/root` (or any `HOME`), so every run logs `unable to
open cache: unable to locate cache directory: neither $XDG_CACHE_HOME nor $HOME are defined` and
falls back to a temporary cache dir instead of persisting one between runs. Backups still
succeed and `restic check` still passes — this only costs a bit of re-work every run, not
correctness. Fix by adding `Environment=HOME=/root` to the `[Service]` section if/when it's
worth the small perf gain; low enough priority that it's been left matching across both existing
hosts rather than fixed on just one.

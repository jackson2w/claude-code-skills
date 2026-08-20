---
name: backblaze-b2-rclone-backup
description: This skill should be used when setting up or debugging an rclone-based backup sync to Backblaze B2's S3-compatible API — especially anything involving Object Lock (immutable/WORM backups), a brand-new B2 account or bucket, or errors like "NoSuchBucket" during a bulk sync, "403 Forbidden" partway through a large job, or "Malformed Access Key Id" from awscli against B2. Sibling skill to cloudflare-r2-rclone-backup (same rclone-to-S3-compatible-provider pattern) — load that one too for the shared flag/config gotchas (--s3-no-check-bucket, --fast-list, --checksum vs --size-only for content-addressed chunk stores). Trigger phrases include "backblaze b2 object lock", "b2 governance mode", "rclone s3-object-lock-mode", "NoSuchBucket bulk sync", "B2 403 Forbidden partway through", "b2 daily class b transaction cap", "b2 caps exceeded", "Malformed Access Key Id aws b2", "b2 master key id format", "rclone concurrent NoSuchBucket", "b2 s3 provider not known".
---

## Object Lock retention does NOT auto-apply from the bucket's default policy

Setting a bucket's `defaultRetention` (via `b2_update_bucket`, `fileLockEnabled: true` +
`defaultRetention: {mode: "governance", period: {...}}`) does **not** cause objects uploaded via
rclone's S3-compatible backend to actually inherit that retention. Confirmed live: objects
uploaded with no explicit lock flags could be deleted immediately afterward by the same
credential that uploaded them, despite the bucket showing a correctly-configured default
retention policy.

rclone requires the retention to be requested **explicitly on every upload**, via two flags that
only take effect together:

```bash
RETAIN_UNTIL=$(date -u -d '+35 days' +%Y-%m-%dT%H:%M:%SZ)
rclone sync SOURCE b2:bucket --s3-no-check-bucket \
  --s3-object-lock-mode=GOVERNANCE \
  --s3-object-lock-retain-until-date="$RETAIN_UNTIL"
```

Per rclone's own backend docs (`rclone help backend s3`): "To enable Object Lock retention, you
must set BOTH `object_lock_mode` AND `object_lock_retain_until_date`. Setting only one has no
effect." `--s3-object-lock-retain-until-date` needs a computed absolute date (moving target each
run, not a fixed value) — compute it fresh in the wrapper script every invocation.

**Verifying retention actually took, without risking real data**: don't just check the bucket
setting or trust a clean upload exit code. Upload a throwaway object, then attempt to delete it
with the *same* scoped credential the sync job uses. A soft delete (adding a delete marker) will
likely still succeed even on a genuinely locked object — that's normal S3 versioning behavior, not
a sign Object Lock failed. The real test is whether a **specific version** can be permanently
purged: `aws s3api delete-object --bucket <b> --key <k> --version-id <id>` (get version IDs via
`aws s3api list-object-versions`) — that should be refused for a properly locked object. Test both
a locked and an unlocked object side by side if the result is ambiguous with just one.

## Concurrent connections can intermittently 404 NoSuchBucket on a real bucket

A `rclone sync` with `--checkers 4 --transfers 2` (fine for Cloudflare R2 — see
`cloudflare-r2-rclone-backup`) can intermittently fail a meaningful fraction of `PutObject` calls
against B2 with a flat `404 NoSuchBucket`, even though the bucket demonstrably exists (single
sequential requests against it always succeed) and even with `--s3-no-check-bucket` already set
(rules out the CreateBucket-preflight issue that flag exists to fix). This reproduces at real
data volume but not with a handful of test files — confirmed via a staged test: 3 tiny files
serial = clean, same 3 files at real concurrency = some 404. Root cause not confirmed
conclusively (most likely multi-replica consistency lag under concurrent load on a
still-relatively-new bucket), but the fix is simple: **`--checkers 1 --transfers 1` (fully
serial)** eliminated the errors entirely at every scale tested, including a real ~65,000-object
sync. Slower, but the only setting that synced real data with zero errors. Revisit concurrency
once a given bucket has more traffic/age history — this may be specific to newly-created buckets.

## New/free accounts have low default daily transaction caps — a real backup job will hit them

Backblaze's free-tier default **Daily Class B Transactions Cap is 2,500/day** (Class C similarly
capped) — a real bulk sync doing per-object `HeadObject` comparison calls across tens of thousands
of files will blow through this in minutes, not days. Symptom: uploads succeed cleanly for a
while (thousands of objects), then **every subsequent write-path call starts failing with a flat
`403 Forbidden`** — no `cap_exceeded` string in the rclone-visible error text, just "Forbidden."
List/read operations (`rclone lsf`) keep working fine throughout, which rules out an account
suspension and points specifically at a capped operation class.

**Diagnosis**: log into the B2 dashboard → Account → **Caps & Alerts**. If a "Daily Class B/C
Transactions Cap" line shows usage over its max (e.g. "2,982 (2,500 max per day)"), that's the
cause — this is a hard stop that resets at the next daily boundary, not a soft rate limit that
backs off and retries successfully.

**Fix**: add a payment method to the account — this removes the free-tier daily caps entirely
(they disappear from the Caps & Alerts page rather than showing "No Cap" for the transaction
classes specifically, though Storage/Bandwidth caps do show "No Cap" explicitly once a card is on
file). **The dashboard says changes take effect in ~1 minute — this was not reliable in practice**:
confirmed still blocked with the identical 403 more than 9 minutes after adding a card and
confirming the caps page had updated. Don't assume propagation completed just because the
dashboard shows the new state and the documented window has passed; if a support ticket is filed,
treat this as needing Backblaze-side confirmation, not just a longer wait.

## AWS CLI rejects B2's master-key-ID format, even though it's valid

`aws s3api` calls using a B2 **master** Application Key's ID (a short, ~12-character string,
notably identical in length/format to the account ID itself) fail client-side with
`InvalidAccessKeyId: Malformed Access Key Id` — before the request even reaches Backblaze. This
is awscli/boto3's own access-key-ID format validation rejecting a key ID shorter than AWS's own
convention expects, not a real credential problem. Confirmed: the exact same master key works
fine against B2's **native** API (`b2_authorize_account` via HTTP Basic auth, no client-side
format check). **Regular (non-master) B2 Application Keys use a longer ID format that passes
awscli's check fine** — this issue is specific to the master key.

If you need to test/use the master key programmatically, prefer B2's native API
(`b2_authorize_account` → `apiInfo.storageApi.apiUrl` for the base URL, `authorizationToken` as a
Bearer-style header value, both in the top-level/nested JSON response — see below) over
constructing an S3-style credential pair from it.

## Native API response shape (v3) — nested, not flat

`b2_authorize_account`'s v3 response nests the useful fields, unlike older API-version docs/blog
posts which show them flat:
```json
{
  "accountId": "...",
  "apiInfo": { "storageApi": { "apiUrl": "...", "s3ApiUrl": "...", "downloadUrl": "..." } },
  "authorizationToken": "..."
}
```
`apiUrl` is at `apiInfo.storageApi.apiUrl`, **not** top-level — a top-level `grep -o
'"apiUrl":"[^"]*"'` will silently match nothing. Use real JSON parsing (`python3 -c "import
json; ..."`), not regex, once the response has any nesting — confirmed this exact mistake
producing an empty `API_URL` with no error, which then made a dependent `b2_list_buckets` call
fail in a way that looked unrelated to the real cause.

`b2_list_buckets` (and most other native API operations) are **POST with a JSON body**, not GET
with query parameters — a GET-with-query-string attempt returns no useful error, just nothing
useful back.

## Misc

- **`rclone: s3 provider "Backblaze" not known - please set correctly`** is a harmless NOTICE
  visible on every command when using rclone's S3-compatible backend against B2 (`RCLONE_CONFIG_*_
  PROVIDER=Backblaze` isn't one of rclone's built-in named presets) — it does not block anything
  and every operation still works correctly. Don't chase it as a real problem.
- **`-v` and `--log-level` are mutually exclusive** in rclone (same gotcha as the R2 skill) — easy
  to reintroduce when copy-pasting a script's flags into an ad-hoc debug command with `-v` tacked
  on.
- **A script designed to rely on systemd's `EnvironmentFile=` for its credentials (the pattern
  used by both this job and the sibling R2 job) will silently run with zero credentials if
  invoked by running the script file directly over SSH instead of via `systemctl start
  <service>`.** rclone's behavior with missing/empty S3 credentials isn't a clean auth error in
  this case — it manifested as `NoSuchBucket` (apparently falling back to some default endpoint),
  which looks exactly like a real bucket/propagation problem and cost significant time to
  distinguish from one. **Always test an EnvironmentFile-dependent script via `systemctl start
  <service>` (or `systemctl restart`), never by invoking the script path directly**, unless the
  credentials are also manually sourced in the same shell first.

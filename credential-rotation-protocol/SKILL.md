---
name: credential-rotation-protocol
description: This skill should be used whenever a live credential (API key, bot token, access token, etc.) needs to be rotated — whether because it leaked, is being proactively refreshed, or is being replaced as part of an incident response. Also load it whenever verifying that a credential file/rotation is correct, since that's exactly the step that causes leaks if done wrong. Trigger phrases include "rotate this credential", "the key leaked", "update this token everywhere", "credential rotation", "verify the new key works", "did the secret change".
---

# Safe credential rotation protocol

Born from a single 2026-07-19 homelab session that required **four rotations** (three of a
Cloudflare R2 key, two of a shared Telegram bot token) because the *verification* step kept
leaking the very credential being verified — via three genuinely different mechanisms
(`rclone -vv`, `cat file | sed 's/FIELD=.../redacted/'`, `ansible-playbook --check --diff`).
Chasing each mechanism reactively (ban `-vv`, then ban `cat`, then ban `--diff`) doesn't scale —
the next leak just needs a fourth mechanism nobody thought to ban yet. This skill exists so
verification *never requires seeing the secret's actual value*, full stop, regardless of which
command someone reaches for.

## The hard rule

**Before running any command whose target is a credential-bearing file, or any host/service
reached using one, ask: "does this command's output structurally contain the secret's actual
value?"** If the answer is anything other than a confident no, don't run it — use one of the safe
patterns below instead. Don't reason about whether *this specific* command "should be fine" —
that reasoning is exactly what failed three times in the incident this skill is named after.

## The complete safe toolkit — every legitimate verification need, none of them can leak

| Question | Safe method | Never use for this |
|---|---|---|
| Did a field in the file change? | Prefix check: `grep '^FIELD=' file \| cut -c1-N` (a handful of characters — enough to confirm a *change*, not enough to be useful if intercepted) | `cat file`, `cat file \| sed 's/.../.../'` or any other full-content dump, however "redacted" |
| Is the file structurally correct (right fields present, none dropped)? | `cut -d= -f1 file` — field **names** only | Anything that shows values |
| Does the new credential actually work? | A real functional test: use it to perform its real action (send a message, make an authenticated API call) with the value sourced into a shell variable (`set -a; source file; set +a`) and *never echoed* — then check the **service's own response**, not local exit code alone | Printing the credential "just to look at it" |
| Is the old/leaked credential actually dead? | The identical functional test, using the **old** value directly — always safe, since that value is already known-compromised; testing it creates no new exposure | N/A, this one is always fine |
| Will a command/playbook change something unexpected? | `--check` / `--dry-run` **alone** — reports changed/unchanged per task, nothing else | `--check --diff`, `--check -v`, or any verbosity flag stacked on top of a dry-run against a credentialed file — the dry-run part is safe, the added verbosity is not |
| Did two values end up equal (e.g. confirming a copy-paste worked)? | Compare **hashes** computed server-side (`sha256sum` on each side, compare the digests — the digest itself reveals nothing) rather than any prefix/value comparison | Diffing or printing either raw value |

If a genuine verification need doesn't fit any row above, don't invent a new one-off command under
time pressure — that improvisation is precisely how each of the three leaks happened. Stop and
ask, or fall back to the least-revealing option that exists (e.g. `-v` over `-vv`, `--check` alone
over `--check --diff`) while flagging the uncertainty explicitly rather than assuming it's fine.

## Rotation checklist

1. **Enumerate every place the credential is used, before touching anything.** A shared
   credential (a bot token, a bucket key reused across several jobs) can have more reach than
   expected. Check project docs for "shared credential" notes, `grep` Ansible playbooks/Terraform
   for the env var name, list Cloudflare Worker secrets, check any app's own credential store
   (n8n, etc.). Discovering a forgotten integration point *after* declaring the rotation done
   means repeating this whole process for something that could have been caught up front.
2. **Generate the new credential** wherever it's actually minted (dashboard, BotFather, `openssl
   rand`, etc.).
3. **The human writes it directly to wherever it needs to live** — never pasted into chat (see the
   global CLAUDE.md secret-handling rule). If the same value needs to land in multiple files,
   write it to all of them in the same sitting rather than trickling out over separate round
   trips — each additional trip is another chance for an unrelated slip during the manual edit
   (e.g. dropping an adjacent, unrelated field by accident — see the `RCLONE_CONFIG_R2_TYPE`
   gotcha in the `cloudflare-r2-rclone-backup` skill for a concrete example of "structurally
   incomplete after a hand edit" biting twice in the same incident).
   - **Not every integration point is a file a human can just edit** — some destinations (a
     Cloudflare Worker secret, an app's own encrypted credential store like n8n's) only accept
     the value through their own API/CLI. For those, the agent can propagate the value safely
     *from* an already-human-provided source, without it ever appearing in the agent's visible
     output:
     - **Worker secrets**: pipe it straight from the source file into `wrangler secret put`,
       never through an intermediate variable that gets echoed: `ssh source-host "grep '^FIELD='
       file | cut -d= -f2-" | wrangler secret put SECRET_NAME --name worker-name`. Confirmed
       working 2026-07-19 propagating a rotated Telegram token to two Workers this way.
     - **An app's own credential-update API**: build the request body **server-side, on the host
       that already holds the source value**, using a small script (Python `urllib`/`requests`,
       not raw shell string interpolation) run over SSH on that host — the value only exists in
       that host's process memory long enough to make the call. See the `n8n-workflow-api-authoring`
       skill's credential-update section for a concrete worked example (`PATCH
       /api/v1/credentials/{id}`).
4. **Verify structurally** — field names all present (step 4 in the table above).
5. **Verify functionally** — a real send/call, reading the *service's* response.
   - **When the integration has no synthetic test endpoint** (a cron-triggered Worker with only a
     `scheduled` handler, a queue consumer with no manual-invoke path), the correct functional
     test is triggering the *real underlying condition* rather than inventing a fake one — e.g.
     stopping the actual monitored service briefly and waiting for the real alert to fire, then
     restarting it. Confirmed working 2026-07-19 for both a Grafana alert rule (stopped
     node-exporter) and a Cloudflare cron Worker (stopped a health-check proxy).
   - **It's OK to end a rotation at "high confidence but not independently fire-tested"** for a
     surface whose real trigger path is genuinely impractical to force (a 30-minute exponential
     backoff, a queue's internal retry-count metadata that can't be set from outside) — *if* the
     code path is confirmed identical to one that *was* fire-tested with the same credential, and
     the credential update itself was confirmed accepted (a 200 response, an `updatedAt` that
     changed). State this honestly as a distinct, weaker confidence level rather than either
     skipping the surface silently or claiming full verification that wasn't actually done.
6. **Verify the old credential is actually dead** — same functional test, old value.
7. **Only after that**, move to the next integration point if there's more than one, repeating
   steps 4–6 for each. Don't declare a multi-surface rotation done until every surface has been
   functionally verified individually — a credential can work in one integration and be
   misconfigured in another.

## Batch, don't trickle

If a rotation is already underway because of a leak and the credential touches multiple systems,
handle all of them in the same sitting rather than discovering integration points one at a time
across hours. Slower, serialized rotations don't just cost time — each one is a fresh opportunity
for the human's manual file edit to introduce an unrelated mistake, and for whoever's verifying to
reach for an unvetted "just this once" command under the accumulated time pressure.

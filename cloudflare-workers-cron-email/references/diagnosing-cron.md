# Diagnosing Cron Trigger registration vs. invocation

Two separate questions, two separate APIs. A Worker can pass the first check
and completely fail the second — that gap is the platform issue described in
SKILL.md.

## 1. Is the schedule registered?

```bash
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME/schedules" \
  | python3 -m json.tool
```

Successful response:

```json
{
  "result": {
    "schedules": [
      { "cron": "0 9 * * 1", "created_on": "...", "modified_on": "..." }
    ]
  },
  "success": true
}
```

An empty `schedules` array means the `[triggers]` block in `wrangler.toml`
never made it into the deploy (or was removed) — that's a config/deploy bug,
distinct from the dispatcher problem below.

## 2. Has it actually invoked?

The dashboard's "Requests" tile and `wrangler tail` are both suspect for this
question (tail can silently reuse a stale session; the dashboard updates with
some lag and doesn't distinguish trigger source in the summary tile). Query
the GraphQL Analytics API directly for real, timestamped invocation counts:

```bash
SINCE="2026-07-04T03:15:00Z"   # start of the window to check
UNTIL=$(date -u +%Y-%m-%dT%H:%M:%SZ)

curl -s -X POST "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"query { viewer { accounts(filter: {accountTag: \\\"$CLOUDFLARE_ACCOUNT_ID\\\"}) { workersInvocationsAdaptive(limit: 50, filter: {scriptName: \\\"$SCRIPT_NAME\\\", datetimeMinute_geq: \\\"$SINCE\\\", datetimeMinute_leq: \\\"$UNTIL\\\"}, orderBy: [datetimeMinute_DESC]) { dimensions { datetimeMinute } sum { requests errors } } } } }\"}" \
  | python3 -m json.tool
```

Notes on this query:

- `datetimeMinute_geq`/`datetimeMinute_leq` are required — omitting a bound
  produces a "cannot request a time range wider than 4w4d" error, since the
  API refuses unbounded historical scans.
- Each row in the result is one minute bucket with at least one invocation;
  sum `sum.requests` across rows for a total count over the window.
- `scriptName` in the dimensions can show as `"__unknown__"` for some request
  types (e.g. plain HTTP fetches to a Worker with no `fetch()` handler) —
  don't be thrown by this; the `sum.requests`/`sum.errors` counts are still
  accurate, just correlate by matching timestamps against what you expect.
- This API has its own account-level rate limits; a 30-second poll interval
  is reasonable when watching for a first invocation to land.

## Ingestion lag: the trap that looks exactly like a broken dispatcher

In one real debugging session, live-polling this exact query every 30
seconds for over 10 minutes showed a flat, unchanging invocation count for a
cron firing every 2 minutes. Re-running the *same query against the same
time window* later showed every single tick present and accounted for, and
the target R2 bucket already contained real output from those runs. The
dispatcher had been working correctly the entire time; the analytics
pipeline simply hadn't finished ingesting recent minutes yet during the live
poll.

**Consequence: a flat/zero reading during active live-polling is not proof of
anything.** Before concluding the dispatcher is broken:

1. Check for a real side effect of the job instead (new/changed object in
   the target bucket, a row written somewhere, etc.) — this is unaffected by
   analytics lag and is the most reliable signal available.
2. If no side effect is visible either, wait substantially longer (step away
   for 10-15+ minutes, not just a longer live-poll loop) and re-run the query
   fresh — don't trust a session that's been continuously polling, since it's
   easy to keep checking the same stale window.
3. Only treat it as a genuine platform issue (see SKILL.md) once both checks
   come back empty after real delay.

## Reading the combined result

| `/schedules` | Real side effect present? | GraphQL invocations (after waiting, re-queried fresh) | Interpretation |
|---|---|---|---|
| empty | — | — | Trigger never deployed — config/deploy issue |
| present | yes | (irrelevant — side effect proves it ran) | Working — don't be fooled by a flat analytics reading during live polling |
| present | no | 0, after a real wait and fresh re-query | Possible platform dispatcher issue — check Cloudflare Community |
| present | no | > 0, but errors present | Code issue — read the actual error via a direct `--test-scheduled --remote` test |
| present | yes/no | > 0, no errors | Working correctly |

#!/usr/bin/env bash
# Query the GraphQL Analytics API for a Worker's actual invocation count over
# a time window — ground truth for "has this cron fired", independent of the
# unreliable wrangler tail / dashboard summary tile.
#
# Usage:
#   CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... \
#     ./check-cron-invocations.sh <script-name> [since-iso8601] [until-iso8601]
#
# Defaults: since = 1 hour ago, until = now.
set -euo pipefail

SCRIPT_NAME="${1:?Usage: $0 <script-name> [since] [until]}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID}"

SINCE="${2:-$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)}"
UNTIL="${3:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

echo "Window: $SINCE to $UNTIL" >&2

RESULT=$(curl -s -X POST "https://api.cloudflare.com/client/v4/graphql" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"query { viewer { accounts(filter: {accountTag: \\\"$CLOUDFLARE_ACCOUNT_ID\\\"}) { workersInvocationsAdaptive(limit: 50, filter: {scriptName: \\\"$SCRIPT_NAME\\\", datetimeMinute_geq: \\\"$SINCE\\\", datetimeMinute_leq: \\\"$UNTIL\\\"}, orderBy: [datetimeMinute_DESC]) { dimensions { datetimeMinute } sum { requests errors } } } } }\"}")

echo "$RESULT" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('errors'):
    print('GraphQL error:', d['errors'], file=sys.stderr)
    sys.exit(1)
rows = d['data']['viewer']['accounts'][0]['workersInvocationsAdaptive']
total_req = sum(r['sum']['requests'] for r in rows)
total_err = sum(r['sum']['errors'] for r in rows)
print(f'total_invocations={total_req} total_errors={total_err}')
for r in sorted(rows, key=lambda r: r['dimensions']['datetimeMinute']):
    print(f\"  {r['dimensions']['datetimeMinute']}  requests={r['sum']['requests']} errors={r['sum']['errors']}\")
"

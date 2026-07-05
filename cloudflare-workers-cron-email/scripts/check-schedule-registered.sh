#!/usr/bin/env bash
# Check whether a Cron Trigger schedule is registered for a Worker script.
#
# Usage:
#   CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... \
#     ./check-schedule-registered.sh <script-name>
set -euo pipefail

SCRIPT_NAME="${1:?Usage: $0 <script-name>}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID}"

curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$SCRIPT_NAME/schedules" \
  | python3 -m json.tool

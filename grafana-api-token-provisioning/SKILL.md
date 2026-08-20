---
name: grafana-api-token-provisioning
description: This skill should be used when provisioning a scoped Grafana API credential for an automation/script (a monitoring sweep, a health-check script, a report generator), when deciding what Grafana role a service account needs, when checking real alert-rule health/evaluation state via the API rather than the UI, or when a Grafana RBAC fixed role like `fixed:alerting.rules:reader` doesn't seem to be assignable. Trigger phrases include "grafana service account", "grafana api token", "grafana read-only token", "grafana alert rule health api", "api/prometheus/grafana/api/v1/rules", "fixed:alerting.rules:reader not available", "grafana RBAC OSS vs enterprise", "grafana viewer role least privilege".
---

# Grafana API token provisioning: OSS role ceiling + useful read endpoints

## OSS has no granular RBAC — Viewer is the floor, not a narrow scope

Grafana's fine-grained fixed roles (`fixed:alerting.rules:reader`, `fixed:alerting.instances:reader`,
`fixed:alerting:reader`, `fixed:annotations:reader`, etc.) are **Enterprise/Cloud-only** — confirmed
against current docs (checked against a live Grafana 13.1.0 OSS install, 2026-07-27). An unlicensed
OSS install can only assign the three basic org roles to a service account: **Viewer, Editor, Admin**.

This means "least privilege" for OSS Grafana tops out at **Viewer** — which reads *all* dashboards,
datasource configs, and alerting state in the org, not just the one thing the automation actually
needs. Say this explicitly when proposing a token to a human ("Viewer is the finest grain OSS
offers, broader than ideal") rather than implying true narrow scoping was achieved — don't oversell
the privilege boundary.

Don't spend time hunting for a way to assign a fixed role via the API on an OSS instance — it's not
a permissions or syntax problem, it's a licensing gate. Check `grafana.ini`/the org's license status
first if genuinely unsure whether Enterprise features are active.

## Creating a service account + token via API (no UI needed)

```bash
# 1. Create the service account (role: Viewer | Editor | Admin)
curl -s -u "admin:$ADMIN_PW" -X POST http://<host>:3000/api/serviceaccounts \
  -H "Content-Type: application/json" \
  -d '{"name":"my-automation-ro","role":"Viewer"}'
# -> {"id":2,"uid":"...","name":"my-automation-ro","role":"Viewer","tokens":0,...}

# 2. Create a token for it (secondsToLive sets expiration; omit for no expiration —
#    prefer setting one, e.g. 31536000 = 1 year, to bound blast radius of a leak)
curl -s -u "admin:$ADMIN_PW" -X POST http://<host>:3000/api/serviceaccounts/2/tokens \
  -H "Content-Type: application/json" \
  -d '{"name":"my-token","secondsToLive":31536000}'
# -> {"id":1,"name":"my-token","key":"glsa_..."}   <- key is shown exactly ONCE, capture it now
```

The `key` field is the only time the raw token is ever returned — if it's lost, delete the token
and mint a new one, don't try to recover it. Pipe the extraction straight into the credential file
in one command (e.g. via `python3 -c 'import sys,json; print(json.load(sys.stdin)["key"])'`) so it
never lands in shell history or chat output — see `credential-rotation-protocol` for the general
"never cat a secret back" discipline this falls under.

Store as `/root/.config/<service>-api-token.env` (`600`, root-owned), same convention as every
other homelab credential (`tailscale-oauth.env`, `immich-admin.env`, etc.) — a plain directory
outside any git repo, doubly safe even before `*.env` gitignore rules apply.

## Useful read-only endpoints for a Viewer-role token

- `GET /api/health` — basic liveness (`database: ok`), needs no auth at all.
- `GET /api/user` — confirms a credential authenticates (`-u admin:$PW` for the admin account
  itself, or `-H "Authorization: Bearer $TOKEN"` for a service account token).
- `GET /api/prometheus/grafana/api/v1/rules` — the Prometheus-compatible ruler API. Returns
  `data.groups[].rules[]`, each with `health` (`ok`/`error`/`nodata`), `state`
  (`inactive`/`pending`/`alerting`), `lastEvaluation`, `evaluationTime`. This is the endpoint for
  "is alerting actually evaluating cleanly" — far more useful for a health-sweep script than
  `/api/health` alone, and works fine under a plain Viewer role. (Grafana 13 is migrating `/api/*`
  toward `/apis/*` long-term, but the legacy path remains fully functional — no urgency to switch.)

Always verify the negative alongside the positive: an unauthenticated call to the rules endpoint
should return `401`, confirming it's genuinely gated rather than coincidentally open.

## Example: turning a "not provisioned yet" warn into a real check

A health-sweep script that can't yet get a scoped credential should emit an honest `warn` explaining
why (not silently skip the check) — then, once a human confirms provisioning is wanted, the checker
should source the token file conditionally and **degrade gracefully back to the warn if the file is
ever missing** (e.g. after a host rebuild), rather than hard-failing the whole sweep on a missing
credential. See the homelab `weekly-housekeeping-checks.sh`'s `grafana_alert_history_scope` check
(added 2026-07-27) for a worked example of this pattern.

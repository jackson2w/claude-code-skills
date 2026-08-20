---
name: grafana-prometheus-alerting
description: This skill should be used when a Prometheus + Grafana stack has metrics being scraped but no real alerting configured, when adding a new Grafana alert rule via provisioning-as-code (not the UI), when checking whether Prometheus alert rules actually exist versus assuming a monitoring stack alerts on its own, when detecting individual systemd service failures across a fleet without building a custom OnFailure-to-webhook mechanism, or when a Grafana alert rule needs testing end-to-end before trusting it. Trigger phrases include "prometheus has no alert rules", "grafana provisioning alert rules", "node_systemd_unit_state", "grafana rules.yaml", "alert on systemd unit failure", "grafana noDataState", "test grafana alert rule firing", "prometheus /api/v1/rules empty", "node_exporter systemd collector".
---

# Grafana native alerting via provisioning-as-code

Covers discovering that a monitoring stack looks complete but doesn't actually alert, and
closing that gap using Grafana's own alerting engine plus metrics `node_exporter` is already
exposing — without building a separate distributed alerting mechanism.

## First, check whether alert rules actually exist

A Prometheus + Grafana + `node_exporter` stack can look fully monitored (dashboards render,
scrape targets show `up`) while having **zero real alerting** wired up. Don't assume rules
exist just because the stack is deployed — check directly:

```bash
# Prometheus's own rules API -- an empty groups list means no rules at all, regardless of
# how populated the dashboards look.
curl -s http://localhost:9090/api/v1/rules | python3 -m json.tool

# Grafana's OWN unified alerting is a SEPARATE thing from Prometheus rule_files -- check this
# too, via a scoped API token:
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  http://<grafana-host>:3000/api/v1/provisioning/alert-rules | python3 -m json.tool
```

If Grafana has exactly one rule (commonly a generic "Host Down" watching `up{job="..."}`),
that only proves the *notification pipe* (contact point → Telegram/email/etc.) works — it
says nothing about individual service failures on an otherwise-healthy host. Don't conflate
"the alerting pipe is proven" with "the fleet is alerted."

## Detect per-service failures without building new infrastructure

Before designing a custom `OnFailure=`-to-webhook mechanism distributed across every host,
check whether `node_exporter`'s systemd collector is already exposing unit state — it often
already is, even without explicit configuration:

```bash
curl -s localhost:9100/metrics | grep node_systemd_unit_state | grep 'state="failed"'
```

If this data is already being scraped by Prometheus, a **single Grafana alert rule** covers
every host and every service with zero new per-host infrastructure — reusing whatever
contact point/notification policy already works. This is almost always simpler and more
maintainable than a distributed alerting mechanism, and it automatically covers any new host
added to Prometheus's scrape config later with no extra wiring.

## Provisioning-as-code rule format

Grafana provisions alerting from YAML files under
`/etc/grafana/provisioning/alerting/{contactpoints,policies,rules}.yaml` (each independently
`ansible.builtin.copy`/`template`-able, `notify`-handler-restarts `grafana-server` on
change). A rule combines a data query (`refId: A`, actual PromQL) with a threshold
expression (`refId: C`, `datasourceUid: __expr__`) evaluating that query:

```yaml
- uid: systemd-unit-failed
  title: Systemd Unit Failed
  condition: C
  data:
    - refId: A
      datasourceUid: prometheus
      relativeTimeRange: { from: 600, to: 0 }
      model:
        expr: node_systemd_unit_state{state="failed"}
        instant: true
        refId: A
    - refId: C
      datasourceUid: __expr__
      relativeTimeRange: { from: 600, to: 0 }
      model:
        type: threshold
        expression: A
        conditions:
          - evaluator: { type: gt, params: [0] }
        refId: C
  noDataState: OK
  execErrState: Alerting
  for: 1m
  labels: {}
  annotations:
    summary: "{{ $labels.name }} failed on {{ $labels.instance }}"
```

**`noDataState` choice matters and is easy to get wrong.** For a rule layered alongside an
existing host-liveness rule (e.g. a generic `up{job="..."} < 1` "Host Down" rule already
covers total scrape failure), set `noDataState: OK` on the new rule rather than the default
`NoData` — otherwise a Prometheus restart blip or a metric that's legitimately absent
double-fires both the specific rule *and* the host-down rule for the same underlying cause.
Reserve `NoData` for a rule that's the *only* thing watching a given failure mode.

If the notification policy (`policies.yaml`) has no label matchers (a single default route),
any new rule automatically inherits the existing contact point with zero additional routing
config — confirm this before assuming a new rule needs its own policy entry.

## Extending coverage to a host outside the normal scrape/inventory pattern

A host added to Prometheus scraping (`job="node"`) is automatically covered by any rule
written against that job label — no per-host rule authoring needed. Confirm a specific host
is actually a scrape target before assuming coverage:

```bash
curl -s http://localhost:9090/api/v1/targets | python3 -c "
import json,sys
for t in json.load(sys.stdin)['data']['activeTargets']:
    print(t['labels'].get('job'), t['labels'].get('instance'), t['health'])
"
```

## Verify a new rule actually fires, don't just trust the YAML

Deploy, then prove it live with a throwaway, harmless failure — don't assume the query
syntax and label matching are correct just because `nginx -t`-equivalent validation passed:

```bash
# A disposable oneshot unit that fails on purpose, on a low-risk host
cat > /etc/systemd/system/alert-rule-test.service <<'EOF'
[Unit]
Description=Throwaway unit to verify an alert rule fires end-to-end
[Service]
Type=oneshot
ExecStart=/bin/false
EOF
systemctl daemon-reload && systemctl start alert-rule-test.service
```

Then poll the rule's live state via the Grafana API until it transitions
`inactive` → `pending` → `firing` (respecting the rule's `for:` duration — don't check once
and give up if it's still `pending`):

```bash
curl -s -H "Authorization: Bearer $GRAFANA_TOKEN" \
  http://<grafana-host>:3000/api/prometheus/grafana/api/v1/rules | python3 -c "
import json,sys
for g in json.load(sys.stdin)['data']['groups']:
    for r in g['rules']:
        print(r['name'], '->', r['state'])
"
```

Clean up the throwaway unit afterward (`systemctl reset-failed <unit>` before removing the
unit file — otherwise the failed state can linger in systemd's own bookkeeping even after the
unit file is gone).

---
name: pihole-dot-upstream-failover
description: This skill should be used when adding DNS-over-TLS (DoT) as a Pi-hole upstream resolver, when evaluating cloudflared for DoT/DoH proxying, when a "no fallback DNS" or "DNS failures should surface" constraint needs to coexist with wanting resilience against a recursive resolver (e.g. Unbound) going down, when pihole-FTL --config dns.upstreams rejects an unquoted value as invalid JSON, or when designing an alerted (not silent) failover watcher for infrastructure that must not silently mask its own failures. Trigger phrases include "cloudflared proxy-dns", "cloudflared DoT deprecated", "pihole DNS over TLS", "stubby DoT", "pihole-FTL --config dns.upstreams", "dns.upstreams invalid JSON", "Unbound fallback resolver", "no fallback DNS constraint", "alerted failover watcher", "silent fallback DNS", "pihole upstream failover".
---

# Pi-hole DoT upstream resolvers: tool choice, config gotchas, and failover design

## `cloudflared proxy-dns` is the wrong tool — don't reach for it

`cloudflared proxy-dns` was deprecated by Cloudflare in November 2025; Cloudflare stopped
shipping it in new `cloudflared` releases as of February 2026 (confirmed via Pi-hole's own docs,
which now carry an explicit deprecation warning on the guide). Existing installs kept working for
roughly 12 months post-deprecation, but it's not safe to stand up fresh.

Independent of the deprecation: `cloudflared proxy-dns`'s `--upstream` flag only ever supported
DoH endpoints (`https://1.1.1.1/dns-query`), **never DoT** (`tls://`). If the goal is specifically
DoT (not DoH), this tool was never the right choice, at any point in its history.

**Use `stubby` instead** — a purpose-built DoT stub resolver, packaged directly in Debian's own
apt repo (confirmed: `stubby` 1.6.0-3.2 on Debian 13/trixie, no third-party repo or GPG key
needed). It's the standard community pattern for "forward only to a specific DoT upstream."

## stubby config gotchas

- **Packaged default listens on `127.0.0.1:53`** (and `::1:53`) — will silently coexist with a
  wildcard `0.0.0.0:53` bind from something else (e.g. pihole-FTL) on Linux, since a
  more-specific bind doesn't conflict with a wildcard one. This is a coincidence of bind
  ordering, not something to rely on — always pin an explicit non-conflicting port.
- **Port syntax on `listen_addresses` is `IP@port`**, e.g. `127.0.0.1@5054` — not `IP#port`
  (that's Pi-hole/Unbound's own convention, easy to cross-contaminate by habit) and not a
  separate config key.
- **Packaged default `upstream_recursive_servers` is a demo/test list** (Sinodun, getdnsapi.net)
  with `tls_pubkey_pinset` entries — replace it entirely for a real deployment. For Cloudflare:
  ```yaml
  upstream_recursive_servers:
    - address_data: 1.1.1.1
      tls_auth_name: "cloudflare-dns.com"
    - address_data: 1.0.0.1
      tls_auth_name: "cloudflare-dns.com"
  ```
  Skip `tls_pubkey_pinset` (hostname validation via `tls_auth_name` is sufficient) — pinning is
  brittle across the upstream's own cert rotations and will silently break resolution when they
  rotate.
- **A broken/invalid `stubby.yml` produces a real crash-loop** (`Could not parse config file:
  ...`), and an Ansible run that only checks for task success (`ok`/`changed`, no failures) will
  look completely clean while the service is actually down. Always verify with `systemctl
  status`/`journalctl -u stubby` after templating a new config, not just the playbook's exit
  code. See the `ansible_managed` gotcha in the global CLAUDE.md's Ansible section for one
  concrete way this happens (a template header silently rendering invalid content while Ansible
  reports success).

## `pihole-FTL --config dns.upstreams` has asymmetric quoting

Setting the value requires quoted JSON strings:
```bash
pihole-FTL --config dns.upstreams '[ "127.0.0.1#5335" ]'
```
An unquoted value (`'[ 127.0.0.1#5335 ]'`) is rejected outright: `not valid JSON`.

But a bare **read** of the same key prints the value **unquoted**:
```bash
$ pihole-FTL --config dns.upstreams
[ 127.0.0.1#5335 ]
```

If you're writing an idempotency check (only write when the live value differs from the target,
to avoid touching FTL on every poll), the read-comparison string and the write-argument string
are **not the same string** — compare against the unquoted read form, but pass the quoted form
when actually setting. Verify this round-trip live with a throwaway set/read before wiring it
into a script; don't assume the two forms match (this is the same quoting idiom used for
`dns.hosts` — see the `pihole-local-dns-records` skill — but that key's *values* are themselves
`"IP HOSTNAME"` strings, so its round-trip masked the same underlying asymmetry differently).

## Designing resilience without violating a "no silent fallback" constraint

If the environment has a standing rule like "DNS failures should surface, not be silently
patched with a secondary resolver" (or any analogous "no silent fallback" infra constraint), an
always-live second upstream (Pi-hole picks whichever responds) violates it even if the intent
was just resilience — a failing primary resolver gets silently absorbed by the fallback with no
signal that anything is wrong.

**Pattern that satisfies both goals** (resilience *and* "failures surface"): an **actively
health-checked, alerted, actuated failover**, not a standing blend:

1. Steady state: primary resolver only, single upstream, unchanged from a no-fallback baseline.
2. A watcher (systemd timer, ~30s interval) runs a **real query** against the primary — not just
   `systemctl is-active`, which misses a wedged-but-running resolver (e.g. broken root hints).
3. On a genuine health-check failure: **clean cutover** (replace the upstream entirely, don't
   blend) to the secondary, plus an **immediate alert** (Telegram, PagerDuty, whatever's already
   wired up) — the human is told the instant the fallback engages, not after the fact via a
   dashboard someone has to remember to check.
4. On recovery: revert, and alert again.
5. State for detecting *transitions* (so you only alert on the edge, not every 30s tick) lives
   on tmpfs (e.g. `/run/<name>/state`), not disk — a reboot always re-verifies live rather than
   trusting stale state across a restart. Default a missing state file to "healthy" so a normal
   boot doesn't fire a spurious recovery alert, while a real ongoing outage at boot still alerts
   correctly (the health check itself is live, not the default assumption).
6. Route the alert directly from the watcher (a raw API call), not through a monitoring stack
   dependency (Prometheus/Grafana alerting) — the failover mechanism and its alert shouldn't
   depend on the monitoring stack being up, especially for infrastructure the monitoring stack
   itself might depend on (e.g. DNS).
7. If this is managed by the same Ansible/config-management tooling that also asserts a baseline
   state, make sure the baseline-assertion task doesn't fight a legitimate in-progress failover —
   only correct the config if it's in neither of the two *recognized* managed states, not
   unconditionally reset to the steady-state default.

Verify this kind of design with a **live** test, not just a config review: actually stop the
primary, confirm an uncached query genuinely fails in the gap before the watcher reacts (proves
the failure really surfaces), confirm the cutover and alert both fire, confirm real traffic gets
served during the outage (check the actual query/access log, not just synthetic test queries),
confirm the secondary path is doing what it claims (e.g. packet-capture the failover traffic and
check for a real TLS record header if it's supposed to be encrypted — `17 03 03` at the start of
the payload, not just "port 853 is being used"), then restore the primary and confirm a clean
revert. If the underlying host can reboot, do that too and confirm both services and the
watcher's own state come back correctly rather than trusting a stale assumption.

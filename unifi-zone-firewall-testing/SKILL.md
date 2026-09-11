---
name: unifi-zone-firewall-testing
description: This skill should be used when testing or verifying UniFi zone-based firewall policies between VLANs, when a ping to a gateway address seems to prove an inter-VLAN policy works, when deciding whether a "blocked" result is a firewall rule or a sleeping device, when a UniFi API write returns HTTP 200 and rc "ok" but the value does not persist, when planning a UniFi cutover and wanting before/after evidence, or when a Guest network appears isolated but has not actually been tested from inside it. Trigger phrases include "test VLAN isolation", "tagged VLAN interface for testing", "SO_BINDTODEVICE no route", "curl --interface blocked", "policy hits counter empty", "last_hit never", "tailscale subnet route breaks my test", "disable the policy to prove it", "index 10000 predefined 2147483647", "test VLAN isolation", "verify firewall policy UniFi", "Trusted to IoT blocked", "guest network isolation test", "UniFi API silently discards", "unifi 200 rc ok not persisted", "inter-VLAN ping works but", "policy matrix before after cutover", "bc_filter_enabled", "mDNS filtering per network", "port_overrides native_networkconf_id", "UniFi zone default block", "deadman revert", "dead man switch network change", "schedule the undo before the change", "renumber the management subnet safely", "locked out of the UniFi controller", "doh state off", "is DNS over HTTPS enabled UniFi", "rest/setting key doh".
---

# Testing UniFi zone firewall policies so the results mean something

Verified against **UniFi Network 10.6.101 / UniFi OS 5.1.31** on a UCG-Fiber with a USW Flex
2.5G and a U7-LR, 2026-09-06. Every claim below was produced with packets, not read from docs.

## The three traps that make a test lie

### 1. Never test against a gateway address

`ping <gateway-IP-on-the-other-VLAN>` from one VLAN succeeds even when that VLAN pair is denied.
Traffic addressed **to the gateway** is local/input-chain traffic, evaluated separately from the
forwarded traffic that zone policy governs. UniFi's own behaviour makes this concrete:

- Port 53 to the gateway is **unblockable** by any policy — it answers on UDP and TCP with every
  allow removed. There is a built-in accept that user policy cannot override.
- Trusted → the Guest gateway SVI succeeds while Trusted → a Guest *host* is correctly blocked.

**Only host-to-host results say anything about a policy.** A gateway SVI test that "passes" is
the single easiest way to certify a firewall matrix that does not work.

### 2. Every assertion needs a control that can fail independently

A device that is asleep and a device behind a working deny rule produce identical silence. iOS
devices in particular go quiet, and a randomised (Private Wi-Fi Address) MAC means the address
you are testing may be a stale lease for a device now on a different one.

The control must reach the **same target** from a path known to be allowed. If the control fails,
the row is **UNTESTABLE** — never pass, never fail. A result that cannot be interpreted must not
be recorded as though it could.

This also means **a bench with one general-purpose host cannot test itself**: the control keeps
collapsing into the test. A second real host is the fix, not cleverer scripting.

### 3. HTTP 200 and `rc: "ok"` do not mean the write happened

This API accepts and silently discards values constantly. Always `GET` the object back and
compare fields. Confirmed silent discards on 10.6.101:

| Write | Read-back |
|---|---|
| `setting/mdns` `enabled_for_network_ids` (either mode) | `[]` |
| `networkconf/<id>` `mdns_enabled: false` | unchanged — it is a **read-only mirror** |
| `setting/mdns` `enabled_for: "custom"` | vestigial; accepted, dropped |

Things that *do* persist: `bc_filter_enabled` on a WLAN, `predefined_services` as
`[{"key":"airplay"}]` with `mode: "custom"` (a **string** list returns `InvalidPayload`), and
`port_overrides` on a device.

The one place it errors honestly is an empty services list under `mode: custom`
(`MdnsSettingInvalidServicesListException`).

## What is actually reachable through the API

- **Zone default is BLOCK.** A pair with no policy is denied, so a matrix that looks complete on
  paper can be missing pairs it needs — an absent `Trusted → IoT` presents on cutover night as
  the entire smart home going unresponsive behind green policies.
- **Per-network mDNS scoping is not reachable via the API.** The feature exists in the UI under
  the name **"mDNS Filtering"** — *not* "Multicast DNS Proxy", which is the gateway reflector and
  the wrong thing to search for. It is **AP-enforced**; the UI bundle carries the strings
  "mDNS Filtering is set to Custom, but some of the selected networks don't exist" and
  "mDNS Filtering isn't supported by any Access Points on this site".
- **Wired VLAN assignment lives in `port_overrides`** on the device object
  (`{"port_idx": N, "native_networkconf_id": "<id>"}`), not in `portconf` profiles.

## Two operational gotchas that cost real time

**A gateway's WAN interface correctly refuses ICMP and HTTPS.** "Cannot ping the WAN address" is
not evidence the gateway lost its lease — check `stat/device` for what the controller says it
holds. Reading "does not answer" as "is not there" sent an afternoon down the wrong path.

**Guest → WAN is unrestricted, and "WAN" means whatever sits upstream.** On a bench where the
house LAN is upstream, a Guest client reaches every host on it, SSH banners included. That closes
when the gateway becomes the edge — but if an ISP router with a management interface sits in
front, Guest reaches it. Add a `Guest → WAN` policy denying RFC1918 destinations.

**Corollary:** a carve-out that appears to work because its target sits on the WAN side has not
been tested at all. A Pi-hole DNS carve-out "passed" from Guest purely because Pi-hole was
upstream and `Guest → WAN` is open; the policy never participated.

## Testing from inside a VLAN you have no device on

A dual-homed laptop can be moved onto the SSID under test. Read the passphrase from
`rest/wlanconf` (`x_passphrase`) and pipe it straight into the join command so it never touches
disk. **Arm an auto-revert before switching**, because the VLAN under test may block the path you
are managing the machine through:

```bash
ssh host "nohup bash -c 'sleep 600; networksetup -setairportnetwork en1 <known-SSID>' &"
```

A wired host changing VLAN keeps its old lease forever under `ifupdown` — arm a DHCP renew loop
before moving the port, or the box strands itself on a network nobody can reach.

## Make the answer discriminate when observation is impossible

Where no observer exists, stop trying to watch packets and design a test whose **answer** differs
by outcome. "Does the gateway resolver use the per-network DHCP DNS?" was settled by pointing one
network's DNS at Quad9 and asking for domains Pi-hole blocks: still `0.0.0.0` meant still
Pi-hole. No capture, no control, no ambiguity.

Watch for caching — use domains never queried through that resolver before, and verify they are
blocked by asking the blocking resolver directly so the cache under test is never primed.

## Give one host every VLAN at once, instead of moving it between SSIDs

Moving a laptop onto the SSID under test works but costs the interface you were using and needs
an auto-revert. If any wired host sits on a **trunked** switch port, a far better instrument
exists — tagged sub-interfaces, several VLANs at once, no gateway or port change to revert:

```bash
ip link add link enp3s0f0 name vl30 type vlan id 30
ip link set vl30 up
dhclient -1 vl30                       # a real lease from the real DHCP server
```

If the port does not carry the VLAN you simply get no lease — a harmless no-op, so this is cheap
to try before assuming you need a port reconfiguration. On UniFi, a default port profile passes
every VLAN tagged with the native one untagged, so this often just works.

**But binding a test to that interface is not enough, and the failure looks exactly like a
policy block.** `curl --interface vlXX` (and anything else using `SO_BINDTODEVICE`) forces egress
on the device — **it does not invent a route**. With the default route still on the physical NIC,
every bound probe fails to connect, and *cannot connect* is indistinguishable from *policy denied
it*. Give each leg its own table:

```bash
ip route add default via 192.168.30.1 dev vl30 table 130
ip rule  add oif vl30 table 130 priority 130
```

**Then assert internet reachability per leg before any interesting row.** `curl --interface vl30
https://1.1.1.1/` must succeed. That single line is the control that discriminates, because it
fails when the plumbing is broken and succeeds when it is healthy.

A cautionary detail: an assertion written *specifically* to catch this can still miss it. A
control requiring "Guest → a Trusted host is blocked, Trusted → same host reaches" is satisfied
perfectly by a **total routing failure** — the physical NIC has an on-link route and the VLAN
legs have none. The control shared the defect it was meant to detect. What exposed it was an
unrelated row claiming Guest could not reach `1.1.1.1:443`, which is plainly false.

Also arm a dead-man's switch before touching routing on a host you reach over that network:

```bash
systemd-run --on-active=480 --unit=revert /bin/sh -c \
  "ip link del vl30; ip route replace default via 192.168.1.1 dev enp3s0f0"
```

## Any host on a tailnet may not be a valid instrument at all

Before trusting any reachability result, check where the packet would actually go:

```bash
ip route get <target>          # Linux
route -n get <target>          # macOS  → look for utunN
```

If a peer advertises the target range as a **Tailscale subnet route**, every probe to it leaves
through the tunnel and never reaches the gateway. Both arms agree, the test looks clean, and it
measured nothing. On one bench this invalidated an entire class of tests from one Mac — while a
second machine on the same bench routed via the gateway and was a perfectly good instrument.

**The instrument was wrong, not the environment.** Concluding "the bench cannot test this" from
one host's defect is the same over-generalisation in reverse. Check the other hosts.

This also threatens **cutover-night verification**: a technician checking inter-VLAN isolation
from a Tailscale-connected laptop gets tunnel answers, so a working block reads as reachable and
an allow passes without the policy participating. Verify from a device with Tailscale off.

## Read `hits`, but never read its absence

Every policy object carries `hits` and `last_hit`, and the populated counters are the cheapest
real evidence available — they exposed a claim filed as "untested, zone empty by design" while
five of its policies had matched thousands of packets.

**An absent `hits` field proves nothing.** Note the distinction: these policies do not report
`hits: 0`, the field is *missing*. A Guest DoT block reporting no counter was demonstrably
matching packets at that moment — proven by toggling it. Missing instrumentation, not missing
traffic.

`last_hit` is worse: several policies report a real `hits` count alongside `last_hit: never`.
Read `hits`; treat `last_hit` as decorative.

## The strongest test of a policy is to turn it off

Behaviour shows a port is shut. It does not show **what shut it** — and the hit counters may not
tell you either. Toggle the rule:

| policy state | `Guest → 1.1.1.1:853` |
|---|---|
| enabled | BLOCKED |
| **disabled** | **REACHED** |
| re-enabled | BLOCKED |

Three data points, ~15 s of propagation each, and the causal claim is closed. Believing a rule
works because its twin on another zone pair works is argument by symmetry — the exact thing
per-zone testing exists to avoid.

## Custom policies always precede the predefined allow

A custom policy is created at `index: 10000`; the predefined `Allow All Traffic` for the same
zone pair sits at `2147483647`. So a new custom rule is evaluated **ahead of** that baseline with
no ordering work. The creation-order warning applies **between customs in the same zone pair** —
create the ALLOW before the BLOCK — not against the predefined rules.

Useful corollary when counting: the API returned 144 policies where only 19 were ours. The rest
are predefined plus auto-created `(Return)` companions. When recording a count, record what was
counted.

## Reference implementation

`scripts/unifi-policy-matrix.sh` and `scripts/cutover-capture.sh` in the homelab repo encode all
of the above, plus `scripts/unifi-private-macs.sh` for finding devices whose randomised MAC has
silently broken their DHCP reservation.

## A DNAT rewrites the destination; it does not grant passage

The sharpest trap in a zone-firewall build with DNS redirection, and it survived a bench that
tested everything else with packets.

A `:53` redirect on a VLAN's ingress rewrites the destination to the internal resolver. **The
resulting flow then crosses zones** — IoT-zone to Trusted-zone — **and this platform's inter-zone
default is block.** Ubiquiti documents that adding a DNAT rule to a **WAN** interface auto-creates
a matching firewall rule; whether that extends into the zone policy table for a **vlan-ingress**
DNAT is undocumented and, as of Network 10.6, unestablished.

**The bench cannot test it if the resolver lives on the WAN side.** `Guest -> WAN` is open, so the
query succeeds and the redirect looks correct while the policy never participates at all — the
same false pass that hid the Pi-hole carve-out. A green result here is evidence about the WAN
allow, not about the redirect.

**Failure mode:** a silent DNS blackhole for every client on the redirected VLANs simultaneously,
presenting as "the internet is broken" and pointing nowhere near DNS.

**Gate it in two parts.** Read the policy table back and confirm an explicit allow exists — do not
assume the DNAT created one. Then check that the query **answers** *and* **appears in the
resolver's log attributed to the client's own IP**. An answer alone can be a leak to an upstream
resolver, which is the failure the redirect existed to prevent.

**Residual to hold to:** keep every DNS DNAT vlan-ingress-only. NAT here is interface-egress-scoped,
so once the resolver's subnet is a LAN subnet the masquerade rule stops matching and attribution is
correct. But a DNS DNAT anchored on the **WAN IP** — the shape you would reach for to catch a
hardcoded `8.8.8.8` — has hairpin semantics whose SNAT half rewrites sources, reintroducing exactly
the mis-attribution you removed.

## The gateway's own resolver follows WAN DNS — test it with an answer that identifies the responder

On UniFi OS 5.1.31 / Network 10.6.101 the client-facing resolver (dnsmasq on every VLAN SVI)
forwards to **whatever Internet 1's DNS is**, not to the per-network DHCP DNS setting and not to
anything policy can reach. Proven 2026-09-07 after an earlier read said the opposite: that
reading was taken inside the ~10–90 s propagation window, the third wrong conclusion that window
produced in one build.

Method that settles it in five minutes, reusable for any gateway resolver question:

1. Pick domains that are **gravity-blocked yet resolve publicly** (`sqlite3 gravity.db "select
   domain from vw_gravity where domain like 'ads.%' order by random() limit 12"`, then keep the
   ones where `dig @1.1.1.1` returns an A record and `dig @<pihole>` returns `0.0.0.0`). The
   answer then names the responder; a plain `example.com` looks identical from either.
2. Baseline `dig @<gateway> <domain-1>`; confirm it shows in Pi-hole's **live** API
   (`/api/queries`), not `pihole-FTL.db`, which lags.
3. Change the lever (here: `PUT rest/networkconf/<wan id>` with `wan_dns_preference: manual`,
   `wan_dns1: 1.1.1.1`), **wait 90 s**, query a never-used domain-2 — a real address means the
   lever moved the resolver; `0.0.0.0` means it did not.
4. Revert, wait, query domain-3, confirm `0.0.0.0` returns and Pi-hole logs it. Never leave a
   bench in a changed state on the strength of the change's HTTP status.

Consequence for a Pi-hole network: **set the gateway's WAN DNS manually to Pi-hole**, or every
client that asks its gateway bypasses the filter. Zone policy cannot block `:53` to the gateway
and a vlan-ingress DNAT excludes gateway-destined traffic, so this is the only lever. Boot order
is not a failover risk: the WAN SLA probes `1.1.1.1`/`8.8.8.8` by address, so Pi-hole being down
fails one probe of three and WAN stays up.

## A WLAN change can silently move your instrument to another SSID

Pinning `AMPJ-IoT-bench` to 2.4 GHz dropped its 5 GHz VAP; the Mac mini's `en1` auto-joined a
*remembered* Guest SSID and the controller kept a stale IoT station entry for it. Every test from
that interface would have measured Guest while labelled IoT. **Check `essid` in `stat/sta` before
trusting any result from a WiFi leg**, and after any WLAN write. `networksetup
-setairportnetwork` may also report "Could not find network" once from scan cache; power-cycle the
radio and retry before concluding the SSID is not broadcasting — the AP's `vap_table` is the
authority for that.

## Schedule the undo before a change that can cost you the controller

A network change can take away the path you would use to reverse it. Renumbering the management
subnet is the clearest case: if devices do not re-inform at the new gateway address, the UI you
would fix it from is the thing you just lost. **Snapshot and schedule the revert first, then make
the change, then cancel the revert** — the same shape as the `systemd-run --on-active=` deadman
used before a lockout-capable `ufw`/`sshd` change.

Reference implementation: `scripts/unifi-deadman-revert.py` in the homelab planning repo, run on
the bench observer host. `arm` snapshots the network object and schedules a restore; `disarm`
cancels and wipes; `fire` restores and **verifies by reading back**, never by trusting the PUT's
return code.

Points that make it real rather than theatre:

- **`fire` must not assume the controller is where it was at arm time** — the reason it is firing
  is that addressing went wrong. Try every plausible address, and **authenticate** rather than
  TCP-probe: something else answering on `:443` satisfies a socket test and proves nothing.
- **Retry across a window.** A DHCP lease can take a minute to follow a subnet change.
- **Unreachable is UNKNOWN, not success.** Exit non-zero and say the revert did not happen.
  A deadman that reports success it did not achieve is worse than none.
- **Refuse to arm without a good snapshot.** Armed-with-nothing is the worst state.
- **Key in tmpfs, 0600, never in argv**, removed on disarm.
- **Verify `disarm` against systemd's own view**, not the stop command's exit code.
- **State the shared failure path in the tool's own output.** This host reverts *over the network
  the change affects*; if its lease does not follow, the rescuer is stranded too. Good net for
  "the change applied but the controller moved", no net for "the segment lost DHCP". Write that
  where the operator will read it, or the tool's existence becomes false confidence.

**Test the failure path, not just the happy one.** Point the candidate list at unroutable
addresses and confirm it exits non-zero with an honest message.

### `doh` is a settings row, not a field

`GET /rest/setting` returns ~38 rows, each with a `key`. DNS-over-HTTPS is
`{"key": "doh", "state": "off", "server_names": [...]}` — a **row whose `key` field is `"doh"`**,
not a field named `doh` on some object. A parser scanning key *names* for `doh` finds nothing and
reports "absent", which reads as reassuring and means nothing. `doh` on would bypass Pi-hole for
gateway-originated queries, which a DNAT structurally cannot close, so a false "absent" here is
expensive.

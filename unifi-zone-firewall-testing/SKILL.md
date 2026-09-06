---
name: unifi-zone-firewall-testing
description: This skill should be used when testing or verifying UniFi zone-based firewall policies between VLANs, when a ping to a gateway address seems to prove an inter-VLAN policy works, when deciding whether a "blocked" result is a firewall rule or a sleeping device, when a UniFi API write returns HTTP 200 and rc "ok" but the value does not persist, when planning a UniFi cutover and wanting before/after evidence, or when a Guest network appears isolated but has not actually been tested from inside it. Trigger phrases include "test VLAN isolation", "verify firewall policy UniFi", "Trusted to IoT blocked", "guest network isolation test", "UniFi API silently discards", "unifi 200 rc ok not persisted", "inter-VLAN ping works but", "policy matrix before after cutover", "bc_filter_enabled", "mDNS filtering per network", "port_overrides native_networkconf_id", "UniFi zone default block".
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

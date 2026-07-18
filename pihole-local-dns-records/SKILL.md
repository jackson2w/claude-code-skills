---
name: pihole-local-dns-records
description: This skill should be used when configuring Pi-hole so devices show by friendly name instead of raw IP in the dashboard/Top Clients/Query Log, when the "List of configured clients" (Group Management > Clients) Comment field doesn't seem to change any display elsewhere, when identifying an unlabeled/mystery device on the network without router access, when a dashboard label doesn't update even though the dns.hosts record looks correct, or when managing dns.hosts declaratively via Ansible. Trigger phrases include "pi-hole map traffic to devices", "pi-hole client names in dashboard", "pi-hole Local DNS Records", "dns.hosts pihole.toml", "pihole-FTL --config dns.hosts", "client comment not showing in dashboard", "pihole network table discover devices", "identify unknown device on network", "what is this IP/MAC", "dns-sd companion-link", "mdns bonjour identify device", "private wifi address randomized mac", "dashboard name not updating", "pihole query log lag".
---

# Pi-hole 6: making devices show by name, not IP

Two different, easily-confused mechanisms live in Pi-hole 6's admin UI:

1. **Group Management → Clients** ("List of configured clients") — assigns a device (by MAC or
   IP) to a blocking group so it gets different blocklists/rules. The **Comment** field here is
   only a label for *your own bookkeeping on this page* — it does **not** propagate to the
   dashboard, Top Clients, or Query Log. This is a long-standing, still-open Pi-hole feature
   request (confirmed via Pi-hole's own Discourse as of 2025/2026) — don't assume setting a
   Comment here accomplishes "friendly names in the dashboard."
2. **Local DNS Records** — a plain IP→hostname map. This is what actually makes the dashboard,
   Top Clients, and Query Log show a name. Requires a **stable IP** (DHCP reservation) per
   device — an IP that later changes leaves a stale mapping, so this is a poor fit for devices
   whose IP isn't reserved (e.g. a phone using Private Wi-Fi Address / MAC randomization with no
   router-side reservation).

## Where Local DNS Records actually live (Pi-hole 6 / FTL v6.7+)

Stored as `dns.hosts` in `/etc/pihole/pihole.toml` — an array of `"IP HOSTNAME"` strings (classic
`/etc/hosts` line format, one string per entry). Read/set safely via the FTL CLI rather than
hand-editing the TOML directly (avoids drift between the file and FTL's in-memory config):

```bash
# read current value
pihole-FTL --config dns.hosts

# set (JSON array of "IP HOSTNAME" strings) — replaces the whole list, not additive
pihole-FTL --config dns.hosts '["192.168.50.211 grafana","192.168.50.196 jellyfin"]'
```

Applies **live, no restart or reload needed** (confirmed repeatedly — a set followed immediately
by a `dig` always reflects the change). Verify with a real forward *and* reverse lookup against
the Pi-hole host itself — don't just trust the command's echoed value:

```bash
dig @127.0.0.1 grafana +short              # forward: expect the IP
dig @127.0.0.1 -x 192.168.50.196 +short    # reverse: expect "jellyfin."
```

Since the command replaces the entire array, always read the current value first and merge in
new entries rather than overwriting with only the new ones.

**Red herring to know about:** chaining several `dig ... +short` calls together in one combined
SSH command can print blank/wrong-looking output for calls after the first, even though
resolution is actually working fine — this looks exactly like a real failure but isn't. Before
concluding a mapping is broken, re-run the specific `dig` call on its own (or drop `+short` for
full output) rather than trusting a blank line from a combined command.

## Finding devices to name, without router access

Pi-hole's own FTL sqlite database already has every device it has seen making DNS queries — MAC,
OUI-derived vendor, IP(s), last-seen time, query count — no router API needed:

```bash
sqlite3 /etc/pihole/pihole-FTL.db "SELECT n.hwaddr, n.macVendor, a.ip, a.name, \
  datetime(n.lastQuery,'unixepoch','localtime') AS lastQuery, n.numQueries \
  FROM network n LEFT JOIN network_addresses a ON a.network_id = n.id \
  ORDER BY n.lastQuery DESC;"
```

**Schema trap:** `network` has no `name` column — only `network_addresses` does (joined via
`network_id`). A query selecting `n.name` from `network` alone throws `no such column: n.name`.
Run `.schema network` / `.schema network_addresses` first if unsure.

Use `numQueries`/`lastQuery` as a quick signal for which devices are real/active vs. transient —
a device seen once with a handful of queries and no OUI vendor match is probably not worth
naming.

## Why some devices already have an empty/no inferred name

A device can appear in the network table with a correctly-identified vendor (e.g. "Apple, Inc."
via OUI lookup) but an empty `name` column — Pi-hole didn't get anything from mDNS/NetBIOS/DHCP
for it. This is common when the device uses Private Wi-Fi Address (MAC randomization, default
since iOS 14) or simply doesn't broadcast a resolvable hostname on this network.

## Never guess device identity from vendor + query volume — verify it

**Real incident:** an Apple-vendor device with by far the highest query count (105k, next
highest was ~35k) was assumed to be "probably the household's Mac" — a plausible-sounding
inference that turned out completely wrong. It was actually an Apple TV (constant background
tvOS/App Store/HomeKit-hub traffic explains the volume). The mistake would have shipped a Local
DNS Record permanently mislabeling one device as another. **High query volume and a matching OUI
vendor are not proof of identity** — both devices in this case were genuine Apple hardware on the
same network; volume alone doesn't distinguish "MacBook" from "Apple TV" from "HomePod."

**Authoritative ways to confirm identity, cheapest first:**
1. **Cross-check against the router's DHCP reservation table** (a screenshot/export from Will,
   since there's no router API access) — reservations show hostname + MAC + IP together and are
   ground truth for anything already reserved.
2. **Check the candidate device directly**, if it's something the user has in hand — e.g. on a
   Mac: `ifconfig | grep "inet 192.168"` shows its actual current LAN IP, settled instantly and
   definitively.
3. **mDNS/Bonjour discovery**, for anything on the same LAN segment that the router can't confirm
   (e.g. no reservation yet) — no router access needed at all:
   ```bash
   # 1. See what service types exist on the LAN
   dns-sd -B _services._dns-sd._udp local.
   # 2. Browse a promising type — _companion-link._tcp (used by tvOS/HomeKit/Handoff) is
   #    unusually good: instance names are often the device's actual human-assigned name
   dns-sd -B _companion-link._tcp local.
   # 3. Resolve a specific instance — the `rpMd=` field is the model identifier
   #    (e.g. AppleTV11,1 = Apple TV 4K 2nd gen, AudioAccessory5,1 = a HomePod)
   dns-sd -L "AMPJ TV" _companion-link._tcp local.
   #    -> resolves to a target hostname like AMPJ-TV.local
   # 4. Resolve that hostname to an IP for the final match
   ping -c1 AMPJ-TV.local
   ```
   Each `dns-sd -B`/`-L` call runs in a loop and needs to be killed after a few seconds if not
   run interactively: `( dns-sd -B ... & PID=$!; sleep 4; kill $PID ) 2>&1`.
   Also useful: `dscacheutil -q host -a ip_address <ip>` for a quick reverse mDNS check first
   (often empty — don't treat that as failure, just move on to the Bonjour browse).
   A device's own Bonjour Computer Name can be cross-checked via `scutil --get ComputerName` if
   it's a Mac you have access to, to rule it in/out as a match for a discovered instance name.

Don't stop at "vendor matches and it's plausible" — one of these concrete checks before writing
any Local DNS Record that claims a specific device identity.

## Disabling Private Wi-Fi Address to unmask a device's real MAC

When mDNS/Bonjour comes up empty (common for iPads and Android devices, which advertise less
than Macs/Apple TVs), the most reliable identification technique for an Apple device with a
locally-administered (randomized) MAC and no vendor match is simply asking the device's owner to
disable **Private Address** for that Wi-Fi network (iOS/iPadOS: Settings → Wi-Fi → (i) next to
the network → Private Wi-Fi Address → off; watchOS: Settings → Wi-Fi → (i) next to the network).
The device then reconnects with its real hardware MAC, which resolves to a genuine vendor OUI —
confirm by checking the new MAC directly against what the device itself reports, not just by
assuming.

**It may take an explicit Wi-Fi reconnect to actually take effect** — toggling the setting alone
doesn't always force an immediate re-association; toggling Wi-Fi off/on (or disconnecting and
reconnecting) on the device reliably does. The device typically gets a **new IP** in the process
(DHCP treats the new MAC as a new client), so watch for a fresh, previously-unseen entry with a
real vendor OUI appearing in Pi-hole's network table around the time of the toggle, rather than
expecting the old IP to just relabel itself.

A quick way to tell whether a MAC is locally-administered (randomized) vs a real vendor OUI
without waiting for Pi-hole's vendor lookup: check the second-least-significant bit of the first
octet. E.g. `66:ea:eb:...` → `0x66` = `0110 0110` — that bit is `1`, meaning locally
administered/private. A real vendor OUI has that bit `0`.

## Pi-hole's per-client dashboard name lags behind a dns.hosts change

Adding or correcting a `dns.hosts` entry doesn't retroactively relabel that client in the
dashboard/Top Clients widget. Pi-hole caches a resolved name per client in
`network_addresses.name`, and — per `resolver.refreshNames` behavior — only refreshes it when FTL
processes a **fresh query from that specific client IP**, not proactively when the static mapping
changes. A client that's been quiet for hours (or that only rarely makes outbound queries) will
keep showing as a raw IP in the dashboard indefinitely, even though `dig`/reverse lookups against
the record itself work fine.

**Fix:** trigger a real query from the client itself (`ssh <host> "getent hosts example.com"` or
similar) and check again. For a host with no shell access (e.g. Home Assistant OS, an appliance
image with no normal root shell), there's no way to force this directly — the label just picks up
whenever that device next makes a real external DNS query on its own (e.g. an update check, though
even that isn't guaranteed to generate one), or after its next DHCP lease renewal if its resolver
changed. This is purely cosmetic — filtering/blocking is unaffected regardless of whether the
dashboard has picked up the name yet.

**Verifying a query landed, without waiting on the slow path:** Pi-hole's long-term SQLite query
log (`/etc/pihole/pihole-FTL.db`, `queries` table) batches writes on a flush interval and can show
*zero* rows for a query fired seconds ago even though it was actually answered — don't mistake
this lag for a real failure. For instant confirmation, grep the live log instead:
```bash
grep 'from 192.168.50.211' /var/log/pihole/pihole.log | tail
```
This updates in real time as `dnsmasq` processes each query, with the querying client's IP
right in the line — far faster feedback than waiting on the DB to catch up.

## Managing dns.hosts declaratively via Ansible

Once a mapping is confirmed, an idempotent Ansible task avoids depending on memory of an ad hoc
`pihole-FTL --config` command run once during troubleshooting:

```yaml
- name: Read current dns.hosts value
  ansible.builtin.command: pihole-FTL --config dns.hosts
  register: current_dns_hosts
  changed_when: false

- name: Set dns.hosts (Local DNS Records) to match desired state
  ansible.builtin.command:
    argv:
      - pihole-FTL
      - --config
      - dns.hosts
      - "{{ pihole_local_dns_hosts | to_json }}"
  when: >-
    current_dns_hosts.stdout | trim !=
    '[ ' + (pihole_local_dns_hosts | join(', ')) + ' ]'
```

The `when` comparison works because `pihole-FTL --config dns.hosts` (no value) echoes the current
list back in the exact format `[ item1, item2, ... ]` — space after `[`, `, ` between items,
space before `]`, confirmed byte-for-byte via `cat -A`. Building that same string from the
desired Ansible list and comparing directly avoids needing to parse TOML/JSON in Ansible at all.
Verified for real idempotency both directions: manually drifting the live config produces
`changed=1` and repairs it; running again immediately after shows `changed=0`.

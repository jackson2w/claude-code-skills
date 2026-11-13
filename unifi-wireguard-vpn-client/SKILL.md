---
name: unifi-wireguard-vpn-client
description: This skill should be used when running or debugging a commercial WireGuard VPN (Proton, Mullvad, etc.) as a WireGuard CLIENT on a UniFi gateway (UCG/UDM) with policy-based traffic routes for chosen devices — sites hang or half-load only while on the VPN, the tunnel's health probes pass but real browsing stalls, an app (WhatsApp media, a bank app) fails only through the tunnel, QUIC/HTTP3 gets no reply, MTU/MSS questions, domain-based VPN bypass, or a watcher that fails over between tunnels. Trigger phrases include "sites hang on vpn", "proton on unifi", "wireguard client unifi", "traffic route kill switch", "vpn bypass domain", "QUIC through VPN", "UDP 443 no reply", "MSS clamp vpn", "mtu black hole wireguard", "probe passes but sites fail", "trafficroutes api", "proton-watch", "vpn degraded".
---

# WireGuard VPN client on a UniFi gateway: what breaks and how to prove it

Built from Will's Proton setup on a UCG-Fiber (Network 10.x, 2026-10-31 → 11-12): three WireGuard
clients (Proton-1/-2 Dallas, Proton-CO), DEVICE-scoped INTERNET traffic routes with the kill switch on,
a watcher (`proton-watch.py`, homelab-ansible) that fails over between tunnels. Memory:
`project_proton_vpn_gateway`.

## Ground rules
- **Never pause or delete a VPN client** to "turn it off": UniFi moves its devices to the WAN at once.
  Toggle the traffic ROUTES instead (`PUT v2/api/site/default/trafficroutes/<id>`, read back: this API
  has silently dropped writes).
- The client's `.conf` holds a private key: the user uploads it in the UI. Never print the
  networkconf `wireguard_client_configuration_file` field.
- Newer IP/DOMAIN routes beat an older INTERNET route for the same device.
- Interface MTU is editable without re-uploading: `PUT rest/networkconf/<id>
  {"interface_mtu_enabled":true,"interface_mtu":1400}`; leak-free.

## The failure classes, in the order they bit
1. **Inner-MTU black hole (provider side).** Some Proton servers silently dropped inner packets of
   1401–1420 bytes (no ICMP), so default MTU 1420 lost them. TCP is saved by the gateway's MSS clamp;
   untrimmed UDP (WhatsApp media over QUIC) just vanished. Fix: interface MTU 1400. Test per tunnel
   from a host whose traffic a probe route sends through it: `ping -M do -s N <probe-ip>` (lost above
   the MTU = as configured) and `-M dont` (large replies inbound).
2. **Probe passes, some sites stall (provider routing, transient).** The tunnel reached Cloudflare
   fine while DataCamp/DigitalOcean sites stalled for ~20 min. A Cloudflare-only probe can't see it:
   probe 2+ non-Cloudflare echo services per tunnel too ("reach" checks) and call the tunnel DEGRADED
   when all fail but the main probe passes. Degraded may move devices to a healthy sibling tunnel,
   but must never fail open to the WAN (a third-party outage would strip the VPN).
3. **QUIC gets no reply through the tunnel (the big one, 11-11).** TCP fine; 16–40% of UDP 443 flows
   via the tunnel got zero bytes back (Google and smaller sites), 0% over the WAN. Apps try QUIC first
   and wait before falling back → "sites hang, then maybe load". Likely the same packet-size class as
   #1: the MSS clamp covers TCP only, QUIC picks its own datagram size and needs PMTUD the provider
   breaks. **Fix: a zone firewall policy REJECT (not BLOCK) udp dst 443 from the VPN devices' reserved
   IPs to External** — reject makes clients fall back to TCP instantly. Result: TCP no-reply 9% → 1.5%,
   "quite zippy". Same trick most VPN apps use.

## Proving it with real traffic, not probes
- `unifi-flows.sh --hours N --out F` (integer hours) → per-flow records. `out.network_name` is the
  egress (tunnel vs `Internet 1`); `traffic_data.bytes_tx` is bytes TO the client (download),
  `bytes_rx` from it. A flow with `packets_rx >= 1` and `bytes_tx == 0` (UDP) or `<= 100` (TCP) got no
  reply. Compare that ratio per route × protocol × destination org over 24 h.
- `getsockopt(TCP_MAXSEG)` after `connect()` shows the clamp: ~1340 via a 1400-MTU tunnel vs 1388–1448
  direct. `mss_clamp: auto` in `rest/setting` (key `usg`) does cover the WireGuard clients.
- `curl --http3-only --resolve host:443:<probe-ip>` tests QUIC through a tunnel (ansible-ctrl's curl
  has nghttp3).
- To test specific sites through a tunnel: clone the watcher's probe route (ansible-ctrl's MAC only,
  kill switch on) with those IPs, test, DELETE it. Gateway write: needs the user's OK / default mode.

## Domain bypass (sites that must skip the VPN)
A DOMAIN traffic route to the WAN for the devices, kill switch off. It only fires when the GATEWAY
answers the lookup, and adds IPs only on a fresh upstream answer (not a cache hit), a moment after
answering. So Pi-hole forwards those domains to the gateway (`server=/d/192.168.50.1`) and the gateway
forwards them to a public resolver via a Forward Domain policy (else it loops back to Pi-hole). Order:
gateway first, then Pi-hole; remove in reverse. `scripts/spectrum-bypass.py` does it.

## Don't
- Don't judge VPN health by the gateway's "CONNECTED" (stayed connected with zero traffic).
- Don't blame DNS caching for "loads now": check whether lookups were already cache hits when failing.
- Don't add an echo service another script relies on for WAN egress (ifconfig.me: the WAN drill).

- **Concurrent pings fake loss.** Two `ping` processes from one host through the same UniFi WireGuard client lose ~50% each (seen on Proton-1 and Proton-2, 2026-11-12); one at a time loses 0. Run one pinger per tunnel.
- **Fresh-connection probes miss idle-connection failures.** If users see apps hang on reused connections while every probe passes, test the same TLS connection after 30–900 s idle (hang = black hole, FIN/RST = fine).

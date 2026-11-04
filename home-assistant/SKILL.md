---
name: home-assistant
description: This skill should be used when configuring, troubleshooting, or extending a Home Assistant OS (HAOS) instance — installing add-ons/apps, editing configuration.yaml, setting up Tailscale/remote access, or troubleshooting onboarding, the Supervisor, or backups, or building automations/scripts/helpers/template switches/webhooks through HA's REST and websocket APIs. Trigger phrases include "Home Assistant add-on", "Home Assistant apps", "configuration.yaml", "HAOS", "Home Assistant Tailscale", "Supervisor", "HACS", "home assistant api", "create automation via api", "/api/config/automation/config", "input_boolean/create", "timer/create", "home assistant websocket", "template switch config flow", "webhook local_only", "ios shortcut webhook", "template value should be a string", "pause for 1 hour then revert".
---

# Home Assistant OS (HAOS)

Operational notes for a Home Assistant OS appliance VM specifically (not a plain Home Assistant
Container/Docker install) — first built in this homelab 2026-07-13 as VMID 150 on Proxmox. For
the Proxmox/Terraform side of provisioning this kind of VM (UEFI, no cloud-init, appliance image
import), see the `proxmox-terraform-provisioning` skill instead — this skill covers the guest
OS/application layer once it's already running.

## "Add-ons" is now "Apps"

Home Assistant renamed **Settings → Add-ons** to **Settings → Apps** in the 2026.2 release —
purely cosmetic (still the same Supervisor-managed Docker containers underneath), done to reduce
confusion between "Add-ons" and "Integrations" for new users. Any guide, screenshot, or memory
referencing "Add-ons" on a current install means **Apps**. Individual app detail pages keep their
existing tab names (Info / Log / Configuration / Documentation) — only the top-level menu label
changed, not the per-app navigation.

## Installing a non-default app

Not every app is in the default store. Community-maintained ones (e.g. the Tailscale app) need
their repository added first: **Settings → Apps → ⋮ (store view) → Repositories** → paste the
repo URL (e.g. `https://github.com/hassio-addons/repository` for the widely-used "Home Assistant
Community Add-ons" set). It then appears in the store under that repo, installs like any other app.

## No normal shell, no cloud-init (guest agent: off until you enable it)

HAOS is a locked-down appliance OS, not a general Debian box:
- No SSH/root shell by default (advanced users can enable an SSH add-on, but treat this as
  intentionally locked down, not a bug).
- Ignores Proxmox cloud-init entirely — onboarding (creating the first admin account) happens
  through HA's own first-boot web wizard, not via injected SSH keys/config.
- **The web UI's port is no longer reliably 8123.** Confirmed on a fresh HAOS 18.2 build
  (2026-08-22): the LAN-facing UI is served on **port 80** by Supervisor's own proxy, while 8123
  itself returns connection-refused from outside the guest (Core is presumably still bound to it
  internally, just not exposed). Symptom if you assume 8123: ICMP ping succeeds, TCP to 8123 is
  refused, but plain `http://<ip>` (port 80) serves the real HA frontend fine — don't read the
  refused 8123 as the guest being down. Check both ports (`nc -zv <ip> 80 8123`) rather than
  assuming one.
- **HAOS ships qemu-guest-agent, but the VM needs `agent: 1`** (Terraform `agent { enabled = true }`).
  Corrected 2026-10-30: the "no working agent" note here was only ever true because the VM was built
  without that flag. Without it, **HAOS ignores ACPI shutdown**: every `qm shutdown` and every pve
  shutdown waited the full 180 s and then SIGTERMed HA, a hard kill that risks its database. With
  it, `qm shutdown 150` took 25 s and `qm agent 150 ping` answers (HAOS 18.4). The flag takes effect
  only after a full VM stop and start, not a guest reboot. Stop it cleanly from HA itself
  (Settings → System → power icon → Advanced → Shut down system), then apply. Without the agent,
  find the IP via `ip neigh` on the Proxmox node, matched by MAC.

## Editing configuration.yaml

Needs a text-editing app first — install one from the default store (no extra repo needed):
- **File editor** — simplest, opens directly into `/config`, `configuration.yaml` is at the top
  level (created by default on first boot).
- **Studio Code Server** — full VS Code in-browser if doing more than a one-line edit.

Always restart Home Assistant (Settings → System → Restart) after editing — changes to
`configuration.yaml` don't take effect live.

## Tailscale access — add-on-based, not raw CLI

Because there's no normal shell, exposing HA over Tailscale goes through the **Tailscale app**
(`hassio-addons/addon-tailscale`, needs the community add-on repo above), not a hand-run
`tailscale serve` command the way every other Debian LXC/VM in this homelab is exposed:

1. Install + start the Tailscale app, authenticate via the login URL shown in its **Log** tab.
   Originally noted as Chrome-only (other browsers reportedly misbehaving with this flow) — not
   reproduced on a 2026-08-22 build, where the same auth link worked fine in Safari. Try whatever
   browser is handy; only fall back to Chrome if the link actually misbehaves.
2. In its **Configuration** tab, show "unused optional configuration options" to reveal:
   - `share_homeassistant`: `disabled` / `serve` / `funnel` — use **`serve`** for tailnet-only
     access (this homelab's standing default — see constraint #3 in `homelab/CLAUDE.md`); only
     use `funnel` if there's a genuine public-ingress need.
   - `share_on_port`: `443` / `8443` / `10000` — `443` matches every other tailnet-only service
     in this homelab.
3. Restart the Tailscale app itself (not just HA) after changing its config.
4. **Trusted proxies must be configured or HA rejects requests coming through the add-on's
   reverse proxy with a plain `400: Bad Request`** (confirmed live 2026-08-22 — direct IP access
   still returned `200` the whole time, only the proxied path 400'd, which is the tell that this
   is what's wrong rather than HA actually being down). Two different mechanisms depending on
   version:
   - **Older versions / still on YAML**: add to `configuration.yaml` via the File Editor app,
     then restart HA:
     ```yaml
     http:
       use_x_forwarded_for: true
       trusted_proxies:
         - 127.0.0.1
     ```
   - **Newer versions (confirmed on the 2026-08-22 HAOS 18.2 build)**: the `http:` YAML key is
     **silently ignored** post-migration — editing it does nothing, no error, and HA shows a
     dedicated warning ("HTTP YAML configuration is ignored after migration ... stops working in
     2027.2.0") the next time you open Settings if you still have a stale block in the file.
     Configure it via **Settings → System → Network → HTTP server → Reverse proxy** instead:
     toggle **Trust X-Forwarded-For** on, add each proxy IP under **Trusted proxies** (as a bare
     IP, e.g. `127.0.0.1` and `192.168.50.181` for a LAN Caddy instance — not a CIDR, despite the
     field's own hint text). Clicking **Save** on that card *is* the restart — no separate
     Settings → System → Restart needed. HA then shows a "Confirm new HTTP server configuration"
     dialog with a ~5-minute auto-revert countdown (a lockout safety net) — click **Confirm** once
     you've verified you can still reach it, or it silently reverts on its own.
   - If proxying through more than one hop (e.g. both a local Tailscale Serve add-on *and* a
     separate Caddy host), list every hop's source IP in trusted proxies — `127.0.0.1` alone
     covers the Tailscale/HAOS-local add-on, but a LAN reverse proxy on another host needs its
     own real IP added too.

## Mobile app setup

Two separate apps are needed, not one:
1. **Tailscale** app — sign into the same tailnet, VPN toggle **on**. If HA "looks down" from a
   phone, check this first — it's almost always the phone's own Tailscale connection status, not
   the HA server (verify server health independently via `curl` from a known-good host before
   assuming an outage).
2. **Home Assistant** companion app — server URL is the Tailscale hostname
   (`https://<name>.<tailnet>.ts.net`), not a LAN IP (LAN IP only works on home WiFi).

## Backup/restore via Proxmox Backup Server

VM-level PBS backup/restore works the same as any other Proxmox VM (`vzdump`/`qmrestore`) with or
without the guest agent. Snapshot-mode backup completed cleanly before the agent was enabled
(2026-10-30); with it on, vzdump also gets an fs-freeze. One restore-test
gotcha: **a `qmrestore` to a throwaway VMID preserves the original guest's MAC address** — booting
it alongside the still-running original puts two VMs on the same LAN segment with an identical
MAC. Strip it first: `qm set <throwaway-vmid> --net0 virtio,bridge=vmbr0` (omit the MAC) so
Proxmox generates a fresh one before starting the throwaway copy.

## Building automations, scripts and helpers through the API (no UI clicking)

Proven 2026-10-31 and 2026-11-04 building the Proton VPN controls (Colorado toggle, per-device
1 h VPN-off switches) entirely from `ansible-ctrl` with a long-lived token. The UI is only needed
to make that token.

- **Automations and scripts are plain REST.** `GET|POST /api/config/automation/config/<id>` and
  `/api/config/script/config/<id>` read and create/replace the whole config (the automation body
  carries its own `"id"`). It's live as soon as the POST returns, with no reload. Keep a `GET` copy
  before replacing anything.
- **Nested templates are rejected.** Writing `{{ … }}` inside another `{{ … }}` fails with `400
  template value should be a string`. Join the pieces with `~` inside a single template instead.
- **Helpers (`input_boolean`, `timer`, …) can't be made over REST.** Use the websocket API:
  `{"type":"input_boolean/create","name":…}`, `{"type":"timer/create","name":…,"duration":"01:00:00","restore":true}`,
  `…/list`. The entity_id is the slugified name. If no websocket library is installed, ~50 lines of
  stdlib Python does it: a `socket` handshake to `/api/websocket`, masked text frames, `auth` →
  `auth_ok`, then one command per `id`.
- **Template switches are config-flow helpers.** `POST /api/config/config_entries/flow`
  `{"handler":"template"}` → `POST …/flow/<flow_id>` `{"next_step_id":"switch"}` → `POST …/flow/<flow_id>`
  `{"name","value_template","turn_on":[…],"turn_off":[…]}` returns `create_entry`. To edit one later,
  use `/api/config/config_entries/options/flow` with its entry_id.
- **Webhook triggers with `local_only: true` reject requests that arrive through a reverse proxy
  or Tailscale Serve,** because the source is a tailnet address. Call the LAN IP on port 80 (HAOS
  serves its UI there). Parse the body defensively:
  `trigger.json if trigger.json is defined and trigger.json is mapping else {}`. An Apple Shortcut
  "Get Contents of URL" set to POST with an empty JSON body arrives as `{}`, so a "no body =
  toggle" design works from both iOS and macOS Shortcuts. The HA iOS app's Shortcuts entity picker
  is unreliable (it offered only lights), so use a webhook.
- **`timer.start` with a `duration` override applies to that one run only.** The next start
  without a duration uses the configured length again (verified). So you can drill a 1 h revert in
  20 s without touching the helper.

### Patterns that held up
- **Switch between two outputs make-before-break.** Turn the target on, wait, then turn the other
  off, so the device is never on zero routes. Every run enables before it disables, which keeps
  `mode: restart` safe under rapid taps.
- **A template switch's state should reflect the intent, not raw entity state, when another actor
  can also move that raw state.** For example, `switch.iphone_vpn` = `input_boolean.iphone_vpn_paused`
  off, not "a route is on", because a failover watcher may turn routes off.
- **A timed pause:** a boolean holds the intent and a `timer` with `restore: true` does the
  revert. A resume automation fires on `timer.finished`, plus a backstop trigger (boolean on for
  duration + 2 min) and HA start with the boolean on and the timer idle. Resume clears the boolean
  **last**, after the route is back on.
- **Gate a safety-net automation with a condition, don't pause it.** When an outside watcher also
  pauses and resumes the same automation, two actors toggling its enabled state will eventually
  undo each other. A `condition: state <pause boolean> off` can't race anything.
- Use `mode: queued` for short set/unset scripts whose runs must not interleave.
- **The UniFi integration sees route changes made outside HA about 10 s late** (it polls). Its own
  changes show instantly. Size any `for:` guard with that lag in mind.
- When a toggle "doesn't work", read the logbook first. A raw entity change shows no
  `script.<x> started` line, which means the user hit the wrong entity, not that the script failed.

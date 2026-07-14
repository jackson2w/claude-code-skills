---
name: home-assistant
description: This skill should be used when configuring, troubleshooting, or extending a Home Assistant OS (HAOS) instance — installing add-ons/apps, editing configuration.yaml, setting up Tailscale/remote access, or troubleshooting onboarding, the Supervisor, or backups. Trigger phrases include "Home Assistant add-on", "Home Assistant apps", "configuration.yaml", "HAOS", "Home Assistant Tailscale", "Supervisor", "HACS".
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

## No normal shell, no cloud-init, no guest agent

HAOS is a locked-down appliance OS, not a general Debian box:
- No SSH/root shell by default (advanced users can enable an SSH add-on, but treat this as
  intentionally locked down, not a bug).
- Ignores Proxmox cloud-init entirely — onboarding (creating the first admin account) happens
  through HA's own first-boot web wizard on port 8123, not via injected SSH keys/config.
- No working QEMU guest agent — don't expect `qm agent <vmid> ping` or IP-readback tooling to
  work; find the DHCP-assigned IP via the host's ARP table (`ip neigh` on the Proxmox node,
  matched by the guest's MAC) instead.

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

1. Install + start the Tailscale app, authenticate via the login URL shown in its **Log** tab
   (open in Chrome on desktop — other browsers are known to misbehave with this flow).
2. In its **Configuration** tab, show "unused optional configuration options" to reveal:
   - `share_homeassistant`: `disabled` / `serve` / `funnel` — use **`serve`** for tailnet-only
     access (this homelab's standing default — see constraint #3 in `homelab/CLAUDE.md`); only
     use `funnel` if there's a genuine public-ingress need.
   - `share_on_port`: `443` / `8443` / `10000` — `443` matches every other tailnet-only service
     in this homelab.
3. Restart the Tailscale app itself (not just HA) after changing its config.
4. **Required in `configuration.yaml`** or HA will reject requests coming through the add-on's
   reverse proxy:
   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 127.0.0.1
   ```
   Restart HA (not just the add-on) after adding this.

## Mobile app setup

Two separate apps are needed, not one:
1. **Tailscale** app — sign into the same tailnet, VPN toggle **on**. If HA "looks down" from a
   phone, check this first — it's almost always the phone's own Tailscale connection status, not
   the HA server (verify server health independently via `curl` from a known-good host before
   assuming an outage).
2. **Home Assistant** companion app — server URL is the Tailscale hostname
   (`https://<name>.<tailnet>.ts.net`), not a LAN IP (LAN IP only works on home WiFi).

## Backup/restore via Proxmox Backup Server

VM-level PBS backup/restore works the same as any other Proxmox VM (`vzdump`/`qmrestore`) despite
the missing guest agent — snapshot-mode backup doesn't require agent-based filesystem freeze to
succeed (confirmed: backup completed cleanly despite `qm agent ping` failing). One restore-test
gotcha: **a `qmrestore` to a throwaway VMID preserves the original guest's MAC address** — booting
it alongside the still-running original puts two VMs on the same LAN segment with an identical
MAC. Strip it first: `qm set <throwaway-vmid> --net0 virtio,bridge=vmbr0` (omit the MAC) so
Proxmox generates a fresh one before starting the throwaway copy.

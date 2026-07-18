---
name: proxmox-no-subscription-nag
description: This skill should be used when a user on a no-subscription (free) Proxmox VE or Proxmox Backup Server install wants to suppress the "No valid subscription" login popup, or asks whether that popup indicates a real problem. Trigger phrases include "no valid subscription popup", "proxmox subscription nag", "remove subscription popup", "proxmox no-nag patch", "checked_command proxmoxlib.js".
---

# Proxmox "No valid subscription" nag suppression

Covers both diagnosing the popup (it's cosmetic, not a misconfiguration) and applying the
widely-used community patch to suppress it — verified live against real PVE 9.2 / PBS 4.2 code
2026-07-17 rather than assumed from older guides, since the exact JS has drifted across
versions.

## It's expected, not a bug

Any Proxmox VE or Proxmox Backup Server host without a paid subscription key shows this popup on
every web UI login. It's a pure upsell nag — every feature works identically without a
subscription; the only thing a subscription actually changes is access to the more conservative
`pve-enterprise`/`pbs-enterprise` apt repos instead of the `*-no-subscription` ones. If a homelab
deliberately runs the no-subscription repos (common — see e.g. this homelab's own note about
disabling the PBS enterprise repo during initial provisioning), the popup is the expected,
correct behavior for that choice, not a sign anything is broken.

## Don't trust a remembered patch snippet — verify the live code first

The patch works by editing the shared `proxmox-widget-toolkit` package's JS (same file, same
package, on both PVE and PBS — confirm the exact path first):

```bash
find /usr/share -iname 'proxmoxlib.js'   # /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
dpkg -S /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js   # confirms owning package for the apt hook below
grep -n "No valid sub" /usr/share/javascript/proxmox-widget-toolkit/proxmoxlib.js
```

Many older forum one-liners (e.g. `sed -i "s/if (data.status !== 'Active')/if (false)/g"`) target
a code shape that no longer matches current releases. As of PVE 9.2.4 / PBS 4.2.3 (2026-07-17),
the actual trigger is a `checked_command` function that calls the `/nodes/localhost/subscription`
API and shows `Ext.Msg.show({title: gettext('No valid subscription'), ...})` when the response
isn't `active`. Always `grep`/`sed -n` the real file on the real host and confirm the surrounding
function shape before writing a patch — don't paste a remembered one-liner blind.

## The patch

Replace the whole `checked_command` function body with a direct passthrough, skipping the
subscription check (and therefore the popup) entirely:

```js
checked_command: function (orig_cmd) {
    orig_cmd();
},
```

Do this with an idempotent script (not a one-shot sed), since the file needs re-patching after
every `proxmox-widget-toolkit` upgrade — apt restores the stock file, and a non-idempotent patch
either double-patches or silently no-ops on the next run. Match on the original
`checked_command: function (orig_cmd) {` marker and an unrelated next-function anchor
(`assemble_field_data: function` in current releases) rather than hardcoding exact internal
whitespace, so minor reformatting between versions doesn't break the match. Keep a rolling
`.orig` backup of the last known stock file for reference/rollback.

No service restart is needed — it's a static file served fresh per request. Just hard-refresh
the browser to bypass any client-side cache of the old JS.

## Persistence across upgrades

Install the patch script somewhere persistent (e.g. `/usr/local/sbin/proxmox-no-nag-patch.py`)
and add an apt hook so it reapplies automatically after the owning package (`proxmox-widget-
toolkit`, confirmed via `dpkg -S` above) upgrades and restores the stock file:

```
# /etc/apt/apt.conf.d/76no-nag-reapply
DPkg::Post-Invoke { "/usr/local/sbin/proxmox-no-nag-patch.py >/var/log/proxmox-no-nag-patch.log 2>&1 || true"; };
```

**Gotcha**: the Claude Code auto-mode permission classifier blocks writes into
`/etc/apt/apt.conf.d/` even via `scp` (a persistent, auto-executing system hook is treated as a
more consequential change than editing one static file, and got blocked separately from — and in
addition to — the file edit itself, which went through fine). Stage the hook file locally and
hand it to the user to `scp`/place themselves rather than retrying the same write repeatedly.
Without the hook, the fix still works, it just needs the same script manually re-run after any
future `proxmox-widget-toolkit` upgrade.

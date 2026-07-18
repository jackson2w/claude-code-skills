---
name: proxmox-vzdump-notifications
description: This skill should be used when customizing Proxmox VE's notification templates (vzdump backup emails, replication, package-updates, test notifications) at /etc/pve/notification-templates/default/*.hbs, when a Handlebars template edit produces mangled output (missing spaces, unexpected blank lines), or when a notification needs to be tested without waiting for or triggering a real backup/replication job. Trigger phrases include "vzdump notification template", "customize backup email", "pve notification hbs", "notification-templates/default", "PVE::Notify", "guest-table hbs", "Handlebars trim eating space", "test proxmox notification without running backup", "human-bytes duration helper".
---

# Proxmox VE notification templates (vzdump and friends)

Proxmox VE 8+ renders its built-in notifications (`vzdump`, `replication`, `package-updates`,
`test`) through Handlebars templates at `/etc/pve/notification-templates/default/`. Each
notification type has three files: `<type>-subject.txt.hbs`, `<type>-body.txt.hbs`,
`<type>-body.html.hbs`. Editing these files (they're cluster config, synced via `/etc/pve`) is
the supported way to change what backup/replication emails look like — no plugin or restart
needed, changes apply to the next notification sent.

Stock/upstream versions live at `/usr/share/pve-manager/templates/default/` for reference if you
need to see Proxmox's own defaults.

**Always `cp` the existing files somewhere (e.g. `/root/notification-templates-backup-<date>/`)
before editing** — there's no built-in versioning, and a bad edit's only rollback path is
whatever copy you made yourself. Keep ownership `root:www-data` and mode `0640` on any replaced
file (`pve-firewall`/notification code runs as `www-data`-group-readable; a stricter mode causes
a silent permission-denied failure on the *next* real notification, not an error now).

Write via a single-line base64 command over SSH rather than a pasted heredoc — the usual
multi-line-SSH-paste-corruption gotcha applies here too (see the global CLAUDE.md SSH/remote
gotchas for the pattern: `echo <base64> | base64 -d > /path/to/file`).

## What data is actually available in the template

For `vzdump`, `PVE::Notify::common_template_data()` (in `/usr/share/perl5/PVE/Notify.pm`) supplies
only `hostname`, `fqdn`, and `cluster-name` (if clustered) — there is no per-job "friendly name",
storage label, or datastore field beyond what's built below. `PVE::VZDump.pm`'s
`send_notification` sub adds the rest of the vzdump-specific fields on top:

- `error` — the error string, or undef/absent on success
- `logs` — full task log text (only meaningfully used in the failure branch)
- `status-text`, `total-size`, `total-time`
- `guest-table` — `{ schema: {...}, data: [ {vmid, name, status, time, size, filename}, ... ] }`
  — one array entry **per guest in that vzdump job**, not per job. If a job backs up a single
  VMID (the common case — separate scheduled jobs per host, staggered a few minutes apart),
  `guest-table.data` has exactly one entry. If a job is configured against a pool or `all`, it's
  one entry per guest.
  - `name` is the guest's actual Proxmox hostname (e.g. `pihole`, `n8n`, `homeassistant`) — there's
    no separate "display name"/friendly-label field, so a template wanting nicer service names has
    to either accept the raw hostname or hard-code a mapping per guest name.
  - `filename` is the raw PBS archive path (e.g. `ct/100/2026-07-15T08:00:01Z`) — technically
    accurate but not a good fit for a "saved to X" sentence aimed at a human; a static, human
    description of the datastore (e.g. "the `pihole-and-friends` datastore on PBS") reads better
    and doesn't require per-guest lookup.

Registered custom Handlebars helpers: `{{human-bytes N}}`, `{{duration seconds}}`, `{{table
guest-table}}` (renders Proxmox's own default table layout in one shot — bypassing it, as a
hand-rolled table/sentence does, is fine and commonly done). Standard Handlebars built-ins work
too and don't need any custom helper: `{{#if}}`/`{{#unless}}`/`{{#each}}`/`{{#with}}`,
`{{lookup array index}}`, and parent-context navigation (`../field`) to reach fields outside a
`{{#with}}`/`{{#each}}` block. There is **no `eq`/comparison helper registered** — you can't write
`{{#if (eq this.name "pihole")}}`; if per-guest branching is needed, `{{lookup guest-table.data
0}}` + `{{#with}}` covers the single-guest-per-job case without needing one.

## Gotcha: `~` whitespace-trim markers can eat a literal space, not just the newline they're meant to strip

Confirmed on PVE 9.2.4 (`handlebars-rust` under `Proxmox::RS::Notify`). This template:

```
{{~#if ../error~}}
err
{{~else~}}
{{this.name}} took {{duration this.time}}
{{~/if~}}
```

renders the success branch as `nametook 42s` — the space between `{{this.name}}` and `took` is
silently swallowed, even though that space is nowhere near the `~` markers (which sit on the
`{{~else~}}` line above). This is **not** a config/typo issue — the raw bytes of the source file
are correct (verified with `od -c`); the trim behavior itself consumes more than the adjacent
whitespace it's documented to strip once combined with a block tag that's alone on its own line.
Removing the `~` markers and restructuring so the interpolation shares a line with its literal
text fixes it with identical visual output otherwise:

```
{{#if ../error}}err
{{else}}{{this.name}} took {{duration this.time}}
{{/if}}
```

**Rule of thumb: avoid `~` trim markers in these templates entirely.** Get rid of unwanted blank
lines by keeping a block tag (`{{#if}}`, `{{else}}`, `{{/if}}`) on the *same line* as the literal
content that follows it, rather than by trimming the newline after it. Verify any template that
does mix interpolation with literal text immediately after a block tag by rendering it for real
(see below) and inspecting the exact bytes — don't eyeball the source and assume it's fine, since
this bug produces no error, no warning, and a diff of the source file looks completely
unremarkable.

## Testing a template change without running a real backup/replication job

Don't wait for the nightly schedule, and don't manually trigger a real `vzdump`/replication job
just to see how a template renders — call the notification system directly with synthetic data
that matches the real shape, routed through the **real** notification config (so it exercises the
actual configured target, e.g. an SMTP relay like Postmark, end-to-end):

```bash
ssh root@pve "perl -MPVE::Notify -e '
my \$template_data = {
    hostname => \"pve\", fqdn => \"pve.local\", error => undef, logs => \"\",
    \"status-text\" => \"backup successful\", \"total-size\" => 123456789, \"total-time\" => 42,
    \"guest-table\" => {
        schema => { columns => [] },
        data => [ { vmid => 140, name => \"homepage\", status => \"ok\", time => 42, size => 123456789, filename => undef } ],
    },
};
PVE::Notify::notify(\"info\", \"vzdump\", \$template_data, { type => \"vzdump\", hostname => \"pve\" });
print \"sent OK\n\";
'"
```

Swap `error => undef` for a real string (and fill in `logs`) to exercise the failure branch. A
perl exception here (rather than `sent OK` + `INFO: notified via target ...`) means the template
itself has a syntax/helper error — that's the signal to fix the `.hbs` file, not the perl one-liner.

**"sent OK" only proves the config accepted it and queued a send — it doesn't prove the rendered
content is correct.** Pull the actual rendered subject/text/HTML back from the notification
target's own API afterward (e.g. Postmark's `/messages/outbound/<id>/details` — see the
`postmark` skill) rather than trusting the perl script's exit status. This is also how the
`~`-trim bug above was actually caught: the isolated perl-triggered send round-tripped through
Postmark and the delivered text body showed the missing space directly, which a "did it error?"
check alone would have missed entirely (it renders successfully, just wrong).

The Postmark SMTP endpoint's credential (if that's the configured target) is at
`/etc/pve/priv/notifications.cfg` (`password` field) and doubles as both SMTP username and
password — same value shown as `username` in the public `/etc/pve/notifications.cfg`.

---
name: homelab-terminal-report-delivery
description: This skill should be used when building or modifying a homelab automation that needs to deliver a status report via email + Telegram + a GitHub-hosted markdown archive — the shared Kanagawa-Wave-terminal-styled report system already used by the weekly housekeeping sweep and the nightly backup summary. Trigger phrases include "homelab status report", "kanagawa wave email", "render-terminal-report", "homelab-report-lib", "consolidate emails into a digest", "add a new homelab report automation", "ghostty styled email report", "claude_code_prompts schema", "push report to obsidian-vault".
---

# Homelab terminal-report delivery system

A shared, reusable pattern for any homelab automation on `ansible-ctrl` that needs to tell Will
"here's the status" via email, a Telegram ping, and a durable GitHub-hosted record — instead of
each automation inventing its own formatting and delivery plumbing. Built 2026-07-18/19 for the
weekly housekeeping sweep, extended 2026-07-19 for the nightly backup summary; reach for it again
before writing a new bespoke report/notification flow.

## What it looks like

Email renders as a Kanagawa Wave-palette terminal window (matches Will's real Ghostty config —
theme "Kanagawa Wave", font "Maple Mono NF") with a macOS-style titlebar, a colored BLUF panel
(`[ OK ]`/`[WARN]`/`[FAIL]` bracket tags, not emoji — they don't grid-align in monospace),
per-category findings, and a "Follow-ups" section at the bottom with one numbered, pasteable
Claude Code prompt per actionable issue. Subject line and Telegram message both read
`❯ <report-name> --date MM/DD/YY`, mirroring the email's own opening prompt line. Telegram is
deliberately minimal (that line + the GitHub report link, nothing else) — full detail lives in
the email and the linked report.

## The pieces (all in `homelab-ansible/scripts/`, deployed to `ansible-ctrl:/root/bin/`)

- **`render-terminal-report.py`** — turns a JSON report object into either the HTML email
  (`--format html`, default) or a plain markdown archive copy (`--format md`). Both formats read
  the exact same JSON, so nothing about the visual design can drift between what gets emailed and
  what gets archived. Takes `--report-name <name>` (e.g. `weekly-housekeeping`, `nightly-backups`)
  which becomes both the titlebar suffix and the `❯ <name> --date ...` prompt line — this is the
  one parameter that makes the script reusable across automations rather than forked per use.
  Usage: `render-terminal-report.py <json_file> <date YYYY-MM-DD> <report_url> --format html|md
  --report-name NAME` (`report_url` may be `""` when rendering markdown before the GitHub push
  that produces it).
- **`lib/homelab-report-lib.sh`** — shared bash functions, sourced by every orchestrator script:
  `send_telegram`, `html_escape` (Telegram `parse_mode=HTML` needs `&`/`<`/`>` escaped), `send_postmark_email` (builds the `HtmlBody`+`TextBody` JSON payload via `jq`, posts to Postmark's API), and `push_report_to_vault <local_md_file> <slug.md> <commit_message>` (commits+pushes into the `obsidian-vault` repo root, prints the GitHub blob URL to stdout, or an empty string on failure — treat empty as "no link available," never as a hard error, matching the report-only never-block-a-delivery-channel posture).
- **The JSON schema** every report is built from:
  ```json
  {
    "overall_status": "ok" | "warn" | "fail",
    "bluf": "2-4 short paragraphs separated by a blank line (\n\n) -- each one scannable idea, not one dense block",
    "claude_code_prompts": [
      {"title": "short label, e.g. 'Investigate pbs SSH host-key change'",
       "prompt": "a complete, self-contained, ready-to-paste prompt for a fresh Claude Code session addressing JUST this one issue -- tell it to read CLAUDE.md first, investigate root cause, propose a fix, apply only after Will confirms"}
    ],
    "categories": [
      {"name": "Category Name",
       "items": [{"status": "ok"|"warn"|"fail", "headline": "short headline", "detail": "one line, optional `code` spans"}]}
    ]
  }
  ```
  `claude_code_prompts` is one entry **per distinct actionable issue**, not one combined prompt —
  the whole point is letting Will paste them into separate Claude Code sessions one at a time.
  Empty array renders no Follow-ups section at all.

## Wiring up a new automation

1. Write (or reuse) a checks script that gathers raw data and decide: does turning that into the
   JSON above need **judgment** (noisy/ambiguous signals that need triage against project
   history — reach for a locked-down headless Claude Code step, see
   [[feedback_claude_cli_disallowedtools_not_allowedtools]] and the weekly housekeeping
   orchestrator for the `--allowedTools`/`--disallowedTools` pattern) or is it **deterministic**
   (a clear pass/fail fact, like "did this vzdump task exit OK" — just build the JSON directly
   with `jq`, no LLM, no API cost, no non-determinism). The nightly backup summary is the
   deterministic template to copy; the weekly sweep is the judgment-step template to copy.
2. Write an orchestrator script (`source` the lib, run the checks, build/receive the JSON,
   validate it with `jq empty`, render markdown → push to vault → get URL → render HTML with that
   URL → send Telegram (`❯ <name> --date ...` + link) → send Postmark (`HtmlBody`+`TextBody`,
   subject `❯ <name> --date MM/DD/YY`)). `set -uo pipefail`, **not** `-e` — a failed delivery
   channel must not block the others.
3. Deploy: versioned copy in `homelab-ansible/scripts/`, live copy in `ansible-ctrl:/root/bin/`.
   An orchestrator that embeds a headless-Claude `--disallowedTools` invocation stays
   **uncommitted**, matching the weekly wrapper's convention; one with no LLM step (like the
   backup summary) is fine to version normally.
4. **Manage the script deployment and the systemd `oneshot` service + `.timer` via the shared
   `homelab-ansible/playbooks/homelab-report-timers.yml` playbook — add a new task block there,
   don't hand-create units on `ansible-ctrl` directly.** Both existing automations
   (weekly-housekeeping, nightly-backup-summary) had their units hand-created initially and it
   took a dedicated fix 2026-07-19 to bring them under Ansible (see
   [[project_nightly_backup_summary]] / [[project_weekly_housekeeping_sweep]] for the incident) —
   a hand-created unit is invisible to a rebuilt `ansible-ctrl` and silently doesn't come back.
   An orchestrator kept uncommitted (the `--disallowedTools` case) still gets its **unit**
   templated by the playbook — only the script copy step is skipped for that one file, referencing
   it in place. `OnCalendar=... America/Chicago` — the host's system timezone is UTC, so the zone
   must be explicit in the calendar expression or it fires at the wrong local hour. Re-run the
   playbook (or `--check --diff` it first) after any future schedule change instead of editing the
   live unit over SSH.
5. If pushing to a **different** GitHub repo than `obsidian-vault`, mint a new dedicated deploy
   key first — GitHub deploy keys are strictly one-key-per-repo (see the homelab CLAUDE.md
   gotcha); reusing `obsidian-vault`'s existing key/alias is fine if the target repo is the same.

## Adding a new check to an existing automation

`categories[]` is freely extensible — a checks script isn't limited to one category. Build the
new check's status/headline/detail the same way as existing ones, add it as its own
`{name: "...", items: [...]}` entry in `categories`, and fold its status into the existing
`overall_status`/`claude_code_prompts[]` logic (fail if any category has a fail, warn if any has
a warn, generate a prompt for anything not `ok`). Verified this works end-to-end 2026-07-19 adding
a "Datastore Capacity" category to the nightly backup summary alongside its existing "Nightly
Backups" category — rendered correctly through `render-terminal-report.py` with no changes needed
to the renderer itself. Always run the checks script standalone first (`| python3 -m json.tool`)
to confirm valid JSON, then push the output through the real renderer before trusting it, rather
than assuming a new category "just works" from reading the schema.

## Dynamic discovery, not hardcoded lists

When a report should automatically pick up new services without editing the checks script (e.g.
"add every configured backup job" rather than "add Pi-hole, n8n, Homepage, Immich by name"),
query Proxmox's own live config as the source of truth — `pvesh get /cluster/backup` for vzdump
jobs, not a maintained list. **`pvesh get /nodes/<node>/tasks` defaults to the 50 most recent
tasks across *all* task types, not just the one you're filtering for** — enough unrelated node
activity between two nights' backup runs silently truncates older-but-still-relevant entries out
of the response before your `jq` filter ever sees them. Always pass an explicit `--limit` (e.g.
300) when cross-referencing task history against a job list you expect to span more than a
handful of the node's most recent tasks.

## Suppressing a per-event notification Proxmox already sends natively

If a new automation is meant to *replace* Proxmox's own built-in notifications for something
(the nightly backup summary replaces the individual per-guest vzdump emails), don't fight the
matcher system with a second decoy matcher — narrow the existing one. Notification matchers'
`match-field` supports `exact:type=<value>` (see `/usr/share/pve-docs/notifications-plain.html`
"Field Matching Rules" locally on the node for the authoritative live syntax — verify against
that file, not memory, since exact CLI flag names have shifted across PVE releases); combined
with `invert-match: true` on the matcher, `match-field exact:type=vzdump` + `invert-match`
means "match everything *except* vzdump" — the single existing catch-all matcher keeps routing
package-updates/replication/system-mail exactly as before, only vzdump stops being delivered
anywhere (an unmatched notification is simply dropped, not queued or retried).
```
pvesh set /cluster/notifications/matchers/<name> --match-field 'exact:type=vzdump' --invert-match 1 --digest <current-digest>
```
Always re-fetch the current `digest` immediately before the `set` call (concurrent-edit guard).
**Verify the suppression actually took effect**, don't trust the API call succeeding: fire a
synthetic notification of the now-excluded type through the *real* config (not a real
backup/replication job — see the `proxmox-vzdump-notifications` skill's `PVE::Notify::notify()`
technique) and confirm via the delivery target's own API (e.g. Postmark's `/messages/outbound`)
that no new message landed, while a different (still-matched) notification type still does.

## Palette

Kanagawa Wave hex values are read directly from Ghostty's own bundled theme file
(`/Applications/Ghostty.app/Contents/Resources/ghostty/themes/Kanagawa Wave` on Will's Mac), not
approximated from memory — re-read that file if the palette ever needs re-deriving (e.g. Will
switches Ghostty themes) rather than reusing the hardcoded hex constants at the top of
`render-terminal-report.py` on faith. Status colors use the *bright* ANSI variants (green
`#98bb6c`, yellow `#e6c384`, red `#e82424`); decorative-only chrome (the titlebar traffic lights)
deliberately uses the *dim* variants so it's never visually confused with real status. `<meta
name="color-scheme" content="dark">` + `supported-color-schemes` are required so mail clients
don't auto-invert the authored dark palette.

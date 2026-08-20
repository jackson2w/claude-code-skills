---
name: claude-code-headless-tool-restriction
description: This skill should be used when building an unattended/headless `claude -p` invocation (cron job, systemd timer, CI step, webhook handler) that needs a real security boundary restricting which tools the agent can use — not just permission-prompt convenience. Trigger phrases include "headless claude code", "unattended claude -p", "restrict claude code tools", "claude code allowedTools", "claude code disallowedTools", "safe automated claude invocation".
---

# Restricting tool access in headless Claude Code invocations

Covers what actually works when a headless/scheduled `claude -p` invocation must be
genuinely prevented from running certain tools (Bash, Edit, network access, etc.) — as
opposed to interactive use, where permission prompts are just a UX convenience. Verified via
direct empirical testing on Claude Code 2.1.214 (2026-07-18); re-verify against the current
version before relying on this for a new build, since this is exactly the kind of CLI
behavior that could change between releases.

## The core finding: `--allowedTools` is not an allowlist

It's tempting to assume `--permission-mode dontAsk --allowedTools "Read,Write"` restricts
the agent to only those two tools. **This is false.** Tested directly: with only
`--allowedTools 'Read Write'` set (no `--disallowedTools`), the agent's Bash tool **still
ran** — `whoami` executed successfully despite Bash never being named in `--allowedTools`.

`--allowedTools` only pre-approves the named tools so they skip permission prompts. It does
not hide or block any tool not on the list. If tool restriction is a real safety requirement
(the agent has SSH/infrastructure access, handles credentials, or runs unattended against
production systems), `--allowedTools` alone provides **no security boundary at all**.

## The fix: `--disallowedTools`, naming every tool explicitly

The only mechanism confirmed to reliably block a tool is `--disallowedTools`, listing it by
name. Both flags are needed together, because they solve two different problems:

```bash
claude --permission-mode dontAsk \
  --allowedTools 'Read Write' \
  --disallowedTools 'Bash Edit Agent CronCreate CronDelete CronList DesignSync EnterWorktree ExitWorktree Monitor NotebookEdit PushNotification SendMessage TaskCreate TaskGet TaskList TaskOutput TaskStop TaskUpdate WebFetch WebSearch Workflow ToolSearch Skill ScheduleWakeup ReportFindings' \
  -p "<prompt>"
```

- **`--disallowedTools`** is what actually blocks tools — confirmed the agent reports them as
  genuinely unavailable ("I have no Bash tool in this environment"), not merely declined.
- **`--allowedTools` is still required alongside it** for any tool that Claude Code treats as
  write-capable/permission-gated (e.g. `Write`, `Edit`). `--permission-mode dontAsk` denies
  those outright unless explicitly allowed — confirmed: `Write` failed with "permission
  denied ('don't ask mode')" when only `--disallowedTools` was set and `Write` wasn't also in
  `--allowedTools`. These are two independent mechanisms, not redundant with each other.
- **Omit `--bare`** if the agent needs to write files. `--bare` silently suppresses the
  `Write` tool entirely regardless of `--allowedTools` — a Write test under `--bare` produced
  no file and no error, just silent failure. (`--bare` otherwise skips hook/skill/MCP
  auto-discovery, which is often desirable for a fixed, predictable unattended task — keep
  using it, just not combined with a Write requirement.)

## Get the full tool list before writing the deny list

Enumerate what's actually available first, so the deny list is complete rather than guessed:

```bash
claude --permission-mode dontAsk --allowedTools 'Read Write' \
  -p 'List every tool name you have access to, one per line, nothing else.'
```

As of 2.1.214 (no `--bare`), the full default set is: `Bash Edit Read ReportFindings
ScheduleWakeup Skill ToolSearch Workflow Write Agent CronCreate CronDelete CronList
DesignSync EnterWorktree ExitWorktree Monitor NotebookEdit PushNotification SendMessage
TaskCreate TaskGet TaskList TaskOutput TaskStop TaskUpdate WebFetch WebSearch`. Include
`ToolSearch` in the deny list specifically — it can load additional *deferred* tools (MCP
connectors, `RemoteTrigger`, etc.) not in this base list at all, and was confirmed blocked
from doing so when disallowed (`ToolSearch: blocked — no ToolSearch tool is available to load
Bash`).

## Why this matters more than it looks

`--disallowedTools` is an explicit deny-list, not a true allowlist — there is no flag
combination found so far that behaves as a genuine strict allowlist. This means:
- The deny list must be **re-enumerated** whenever a Claude Code upgrade adds new tools this
  version doesn't have yet, or a newly-added tool silently slips through unblocked.
- **Never trust `--allowedTools` alone as a security boundary**, no matter how narrow the
  allowed set looks. Always verify with a direct test (try to run something outside the
  intended scope, like `whoami` via Bash) before trusting a new unattended invocation with
  real credentials or infrastructure access.

## Verifying the combination actually works

Before shipping any unattended job built this way, run a direct adversarial test — don't
just trust the flags:

```bash
claude --permission-mode dontAsk \
  --allowedTools 'Read Write' \
  --disallowedTools '<full deny list>' \
  -p 'First try to run "whoami" via Bash. Then try to write OK to /tmp/test.txt via Write. Report exactly what happened.'
```

Expect: Bash reported as unavailable/blocked, Write succeeds and the file is actually
created (verify on disk, don't just trust the model's claim).

## Real-world reference implementation

Built for the homelab's weekly automated housekeeping sweep — a headless Claude Code
invocation on a systemd timer that reads a read-only fleet-check script's JSON output plus a
CLAUDE.md gotcha file for context, and writes a report, with zero ability to run Bash/Edit/
network tools against the actual infrastructure. See `homelab-ansible/scripts/weekly-housekeeping-run.sh`
(graduated into version control 2026-08-17 — deployed to `/root/bin` on `ansible-ctrl` via
`homelab-report-timers.yml`; previously kept local-only/uncommitted over a since-superseded
worry about committing its `--disallowedTools` flags, which aren't secrets) for the full
working wrapper.

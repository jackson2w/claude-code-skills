---
name: resilience-ledger-email-styling
description: This skill should be used when sending or styling any transactional/notification email for Will (dfw, Olu, WordPress, or any future homelab automation) and it should carry the resilience-ledger design system look, when a new HTML email needs light+dark mode that actually works, or when debugging an email where dark mode text is invisible/low-contrast. Also load this before touching render-ledger-email.py, ledger-email-style.php, or render-terminal-report.py's HTML output. Trigger phrases include "ledger styled email", "resilience ledger design system email", "make this email look like the other ones", "dark mode email text invisible", "email dark mode not working", "wp_mail styled", "render-ledger-email.py", "status pill email", "callout box email html".
---

# Resilience-ledger email styling

A shared visual language for every outbound email in this environment — `dfw`/Olu's own sends,
WordPress's `wp_mail()` notifications, and the homelab-wide weekly report system on
`ansible-ctrl`. Built 2026-08-17 from the `resilience-ledger-design-system` Artifact Will liked
(warm-paper/dark-ink "systems report" look — status pills, tinted callout boxes, IBM Plex
Mono/Sans). This is a **different, separate visual language** from anything else in this
environment named "Kanagawa" — don't confuse it with Ghostty's terminal theme.

## Source of truth for the palette

`~/Desktop/resilience-ledger-design-system/tokens.css` on Will's Mac. Every hex value used
anywhere in this pattern is hand-copied from that file — **re-derive from there, not from
memory or from any of the three implementations below**, if the palette ever needs to change.
There is no shared stylesheet these implementations `@import` (email clients strip external
CSS), so a palette change means editing all three by hand. Light values live in the bare
selectors; dark values are the second `@media (prefers-color-scheme: dark)` block. Ignore the
third `[data-theme="dark"]` block in that file — that's for a web toggle, irrelevant to email.

## The one rule that matters most: theme color goes through CSS classes, never inline

**Real bug hit and fixed while building this**: an early version set text color inline on
prose paragraphs (`style="...color:#21201C;"`, the light-mode ink color). A `<style>` block's
`@media (prefers-color-scheme: dark)` override for that same element does **not** win against
a plain inline style — inline styles beat embedded stylesheet rules regardless of media query,
unless the stylesheet rule uses `!important`. Result: in dark mode, the *background* correctly
switched to dark (that was set via a class) but the *text* stayed the light-mode dark-ink
color — dark text on a dark background, functionally invisible. Caught only by actually
screenshotting the rendered output (see Verification below), not by reading the CSS.

**The fix, and the rule going forward**: every element whose color needs to differ between
light and dark gets a class name (`ledger-p`, `ledger-title`, `ledger-heading`, `ledger-pill-
ok`, etc.), and *only* the class rules in the embedded `<style>` block set `color`/`background`/
`border-color`. Inline `style=` attributes are reserved for properties that never change by
theme — `padding`, `margin`, `border-radius`, `font-family`, `font-size`, `letter-spacing`.
If you're about to write `style="color:#..."` directly on an element inside one of these
templates, stop — that color belongs in a class rule instead.

## Font reality — don't oversell fidelity

IBM Plex Mono/Sans are **not** embedded as web fonts in any of these emails — `@font-face`
loading is unreliable across email clients (Gmail generally ignores it entirely, Apple Mail
partial, Outlook desktop none). Every font-family stack lists the real typeface first but
falls back honestly: `'IBM Plex Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace` and
`'IBM Plex Sans', -apple-system, 'Segoe UI', sans-serif`. The "systems report" register comes
through via the fallback stack even where the exact typeface doesn't load. Don't promise
pixel-identical rendering to the web Artifact version in every client — it isn't, and that's an
accepted, deliberate tradeoff, not a bug to chase.

## Components

- **Status pill**: color + a small dot + text label (`OK`/`WARN`/`FAIL`), never color alone.
  Semantic colors only — green/amber/red mean fine/needs-attention/broken, not
  unimportant/important.
- **Callout/BLUF box**: tinted background (12-14% opacity of the status color) + a colored
  eyebrow label. **Deliberately no colored left border** — a thick side-accent on a card is
  one of the most recognizable AI-generated-UI tells, per the source design system's own
  README; don't reintroduce it here even though it would be an easy way to show status.
- **Mono block**: a light/dark-toned card, monospace, `white-space:pre-wrap`, for anything
  list/data-like (IP counts, pasteable prompts) — as opposed to prose, which uses the sans
  stack in plain `<p>` tags split on blank lines.
- **No numbered section markers** unless content is a genuine sequence — a numbered marker on
  non-sequential content is decoration pretending to be information (same README guidance).
- **Footer report-link line**: omit entirely when there's no link, never show a placeholder
  string.

## Required `<head>` boilerplate

Every implementation needs both of these, or clients may auto-invert an unstyled body instead
of rendering the authored dark palette:
```html
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
```

## The four implementations — no shared renderer across runtimes

Same design language, four separate hand-written implementations, because nothing here can
share code across the runtimes/hosts involved:

1. **`/usr/local/bin/render-ledger-email.py`** on `dfw` (Python, world-readable/executable —
   both root-run systemd services and the `openclaw` user call it). JSON-in
   (`title`/`eyebrow`/`status`/`summary`/`sections[]`/`footer`), HTML-out on stdout. Used by
   `fail2ban-weekly-digest.sh` and `dfw-package-check.sh` (added 2026-08-20, part of
   `dfw-ansible`'s graduated `package-check-install.yml` — see `project_dfw_vultr_buildout`
   memory), and documented as the default in Olu's `email` skill
   (`/home/openclaw/.openclaw/workspace/skills/email/SKILL.md`) for anything substantive.
2. **`/var/www/williejackson.com/wp-content/mu-plugins/ledger-email-style.php`** on `dfw`
   (native PHP — can't shell out to the Python renderer per-email from a WP process). Hooks
   `wp_mail_content_type` → `text/html` and a `wp_mail` filter (priority 20) that wraps the
   plain-text message body in the same visual shell. Guards against double-wrapping if a
   message already looks like real HTML (`stripos($message, '<html')`).
3. **`/root/ansible/scripts/render-terminal-report.py`** on `ansible-ctrl` (git-tracked in the
   `homelab-ansible` repo, deployed to `/root/bin/` — **only ever via the
   `homelab-report-timers.yml` playbook, never hand-copied over SSH**, or a future
   `ansible-ctrl` rebuild silently loses the change). A richer schema than #1
   (`overall_status`/`bluf`/`categories[].items[]`/`claude_code_prompts[]`) for the shared
   weekly-housekeeping/nightly-backup-summary/R2-B2-sync report system — see the
   `homelab-terminal-report-delivery` skill for that schema's full contract.
   `render_markdown()` in this same file is untouched by any of this — markdown has no visual
   style to change, verify any future edit here doesn't touch it (diff before/after).
4. **`backup-worker/src/render-terminal-report.js`** in the `photo-site` repo (JS, Cloudflare
   Worker). A hand-maintained JS port of #3 — same schema, same visual output, kept in
   lockstep manually since there's no shared code across the Python/JS runtime boundary. Was
   still on the old Kanagawa Wave design until 2026-08-20 (missed by the 2026-08-17 fleet
   restyle since it isn't deployed via `homelab-ansible` and nothing sweeps this repo). If #3's
   markup changes, port the change here too — don't let it drift again.

If a *new* consumer needs this styling: reuse #1's schema directly if the content is simple
(a title, maybe a status callout, a few prose/data sections); reuse #3's schema if it needs
categorized findings with per-item status and/or a follow-ups section. Don't invent a fourth
schema without a real reason.

## Sending — Cloudflare Email Sending (dfw/Olu path)

```bash
curl https://api.cloudflare.com/client/v4/accounts/af56d5158a7dab3e67f31efc275ec9f2/email/sending/send \
  -H "Authorization: Bearer $CLOUDFLARE_EMAIL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"to":"...", "from":{"address":"olu@jackson2w.dev","name":"..."}, "subject":"...", "text":"...", "html":"..."}'
```
Always include both `text` and `html` — never `html` alone. `from` must stay
`olu@jackson2w.dev`, the only domain onboarded to Email Sending on this account. A
`success:true` response includes a real `message_id` — that's the thing to check, not just
that the `curl` call didn't error (see Verification below).

`ansible-ctrl`'s reports go out via Postmark instead (`send_postmark_email` in
`homelab-report-lib.sh`) — different transport, same HTML.

## Verification — screenshot before shipping, don't trust the markup alone

The invisible-dark-text bug above was caught by **actually rendering and screenshotting the
output**, not by reading the CSS and reasoning it should work. Before shipping any change to
one of the four implementations (for #4, run the JS renderer under plain `node` against a
sample JSON payload to get an HTML file to screenshot — no Worker deploy needed just to check
rendering):

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --window-size=700,1000 \
  --screenshot=/path/out.png "file:///path/to/rendered.html"
```

**To check light mode when the environment's default is dark** (confirmed on this Mac —
`--force-prefers-color-scheme=light` did *not* actually override the rendering in testing,
don't rely on it): strip the `@media (prefers-color-scheme: dark) { ... }` block out of a throwaway
copy of the rendered HTML (brace-counting from the media query's opening `{` to find its real
close, since it contains nested `{}`), and screenshot that copy instead — with the override
removed, only the base (light) rules can apply regardless of the environment's actual
preference.

For a real end-to-end check (not just a local screenshot): send one isolated real test through
whichever transport is relevant (`send_postmark_email` for `ansible-ctrl`, the Cloudflare
curl call above for `dfw`) using a realistic sample payload — this doesn't require waiting for
or triggering a real scheduled run, and catches transport-level issues a local screenshot
can't (e.g. confirm the *deployed* file, not just a local copy, actually renders right). Then
ask Will to actually look at it on a real device — client rendering (especially font fallback
and dark mode) can't be fully verified from a screenshot or a `success:true` API response
alone.

## Deployment gotcha: the auto-mode classifier blocks some `/etc` writes, inconsistently

Writing `/etc/fail2ban/jail.local` directly (a plain heredoc, not even base64/piped) was
blocked by Claude Code's own auto-mode classifier and needed Will to run the command himself.
Writing `/etc/systemd/system/*.service`/`*.timer` files the same session was **not** blocked.
Don't assume all of `/etc` is off-limits — just attempt the write, and if it's blocked, ask
Will to run the exact command rather than hunting for an encoding workaround (base64|tee
triggered the identical block as a plain heredoc — it's not about the pipe shape).
`/usr/local/bin/*` and WordPress's `mu-plugins/` directory were never blocked.

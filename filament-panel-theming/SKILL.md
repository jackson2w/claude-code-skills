---
name: filament-panel-theming
description: This skill should be used when applying a custom color palette, self-hosted fonts, or a brand name to a Filament v3 admin panel — anything beyond the stock Tailwind-gray/Inter/Amber default. Covers `php artisan make:filament-theme` recommending the Tailwind v3 CLI instead of Vite when the host app is on Tailwind v4, `->theme()` vs `->viteTheme()`, which Filament surfaces are re-themable via `FilamentColor`/`Color::hex()` versus literal Tailwind colors needing direct CSS overrides on `fi-*` component classes, self-hosting fonts via `LocalFontProvider`, and `->brandName()`. Also covers a second, more specific mixed-content bug than the one in `laravel-filament-proxmox-lxc`: `asset()` not honoring `URL::forceScheme('https')` even after that skill's fix is already in place. Trigger phrases include "skin the filament panel", "filament custom theme", "filament design system", "make:filament-theme", "filament Tailwind v4 conflict", "filament bg-white not themed", "filament dark:bg-gray-900 override", "FilamentColor register", "Color::hex generate palette", "filament LocalFontProvider", "self-hosted fonts filament", "filament brandName", "filament fi-section fi-sidebar override", "asset() secure true", "theme.css http:// mixed content".
---

# Filament v3 panel theming — custom color, fonts, and chrome

Built and verified skinning the Homelab Console app (Filament v3.3) with a bespoke "Resilience
Ledger" design system — every gotcha below was hit for real. Distinct from the
`laravel-filament-proxmox-lxc` skill, which covers *deploying* a Filament app; this one covers
*reskinning* an already-deployed panel. Read the vendor Blade source directly when in doubt
(`vendor/filament/*/resources/views/...`) rather than guessing class names from memory — Filament
class names are stable across versions but not documented exhaustively, and the actual
`bg-white`/`dark:bg-gray-900` utility classes only show up by reading the real templates.

## Scaffolding the theme: `make:filament-theme` and the Tailwind v3/v4 conflict

`php artisan make:filament-theme <panel-id> --pm=npm --no-interaction` scaffolds
`resources/css/filament/<panel>/theme.css` + a matching `tailwind.config.js`. If the host app was
created with a recent `laravel new` (Tailwind v4 by default), the command detects the mismatch —
**Filament v3's theme system requires Tailwind v3** — and prints the exact fallback command
instead of erroring:

```bash
npx tailwindcss@3 --input ./resources/css/filament/admin/theme.css \
  --output ./public/css/filament/admin/theme.css \
  --config ./resources/css/filament/admin/tailwind.config.js --minify
```

This works even though `package.json` never gets a `tailwindcss@3` devDependency — `npx` fetches
it standalone on first run and caches it. Don't downgrade the app's real Tailwind v4 install to
work around this; the standalone CLI coexists fine.

**Register with `->theme(asset('css/filament/admin/theme.css'))`, not `->viteTheme(...)`.**
`viteTheme()` expects a Vite-built asset with a manifest entry — this path never produces one
(the CLI writes directly to `public/`, bypassing Vite entirely). `->theme()` just needs a plain
URL to a compiled CSS file. The compiled `public/css/filament/admin/theme.css` **is** meant to be
git-tracked (only `/public/build`, the Vite output dir, is normally gitignored) — there is no dev
server watching this file, so re-run the CLI command and commit the output after every edit to
the source `theme.css`.

If the LXC/VM has no Node.js at all (a PHP-only box, common for a Filament app not otherwise
needing a JS runtime), install it as a **build-time-only** tool — NodeSource apt repo is fine,
same as `proxmox-node-systemd-service` uses for actual Node services, but no systemd unit is
needed here since nothing runs it continuously.

## The `asset()` mixed-content gap (beyond `URL::forceScheme`)

If the app is already running behind a TLS-terminating reverse proxy (Tailscale Serve, Caddy)
with `URL::forceScheme('https')` set in `AppServiceProvider::boot()` — see
`laravel-filament-proxmox-lxc`'s mixed-content section for why that's there — know that this
**does not cover the plain `asset()` helper**. Filament's own internally-generated asset URLs
(the core CSS/JS bundles from `@filamentStyles`/`@filamentScripts`) correctly resolve to
`https://`, but a raw `asset('css/filament/admin/theme.css')` call inside a panel provider's
`->theme()`/`->font()` still emits `http://` — silently blocked by the browser as mixed content,
with **zero errors anywhere**: `curl` returns clean 200s (curl doesn't enforce mixed-content
policy), Laravel's log stays empty, and the page renders structurally correct but completely
unstyled, easy to mistake for the CSS itself being broken rather than never having loaded.
Diagnose by checking the actual `href=` scheme in the rendered HTML
(`curl -s <url> | grep -o 'href="[^"]*\.css[^"]*"'`), not by trusting a 200 status.

Fix: pass `secure: true` explicitly as the second argument on every `asset()` call in the panel
provider:

```php
->font(
    'IBM Plex Sans',
    url: asset('css/filament/admin/fonts.css', secure: true),
    provider: \Filament\FontProviders\LocalFontProvider::class,
)
->theme(asset('css/filament/admin/theme.css', secure: true))
```

`asset($path, $secure)` accepts `$secure` as an explicit override — when non-null it bypasses
scheme *detection* entirely (request scheme, forceScheme, everything) and just emits
`https://`/`http://` directly. This is more reliable than debugging why `forceScheme` isn't
propagating to this particular helper.

## Self-hosted fonts via `LocalFontProvider`

```php
->font(
    'IBM Plex Sans',
    url: asset('css/filament/admin/fonts.css', secure: true),
    provider: \Filament\FontProviders\LocalFontProvider::class,
)
```

`LocalFontProvider::getHtml()` is trivial — it just emits `<link href="{$url}" rel="stylesheet"
/>`, no parsing or validation of the URL's contents. The font family name passed as the first
argument sets Filament's `--font-family` CSS custom property (consumed by the Tailwind preset's
`fontFamily.sans`), independent of what's actually declared in the linked stylesheet — the two
must agree (the `@font-face font-family` inside the CSS should match the string passed here) but
Filament doesn't verify this for you.

If a font is already self-hosted elsewhere as base64-embedded `@font-face` WOFF2 (e.g. inside a
published design-system Artifact or an existing ledger-styled-email renderer), extract those
exact `@font-face` blocks rather than re-fetching from Google/Bunny Fonts or Fontsource — byte-
identical to what's already shipping elsewhere, and no new network dependency at build or runtime.
Filament only needs weights actually used by its own components plus whatever custom CSS
overrides reference (typically 400/500/600/700 covers everything).

There is no equivalent panel-level hook for a custom **monospace** family — if the design uses
one (code blocks, an "eyebrow" label style, badges), extend the Tailwind config directly instead:

```js
theme: {
    extend: {
        fontFamily: {
            mono: ['var(--font-family-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        },
    },
},
```
with `--font-family-mono` defined in `theme.css`'s own `:root`.

## What's actually re-themable vs. what needs a direct CSS override

`$panel->colors(['primary' => '#4A6FBE', 'gray' => '#6B6656', ...])` accepts either a full
50–950 shade array or a plain hex string — a hex string auto-generates the full ramp via
`Color::hex()`/`Color::generateShades()`. This covers `primary`/`success`/`warning`/`danger`/
`info`/`gray`, each surfaced as CSS custom properties (`--primary-500`, etc.) that Filament's own
Tailwind preset consumes as `rgba(var(--primary-500), <alpha-value>)`.

**`gray` is the highest-leverage slot for whole-panel re-tinting**, not just table/badge accents:
the panel body itself (`<body class="fi-body ... bg-gray-50 ... dark:bg-gray-950 ...">`) uses the
`gray` scale's extremes directly. Registering a brand-tinted gray (e.g. a warm neutral hex instead
of a cool default) re-tints the entire page background/border/muted-text system for free, in both
light and dark mode, with one line — confirmed by reading `vendor/filament/filament/resources/
views/components/layout/base.blade.php` directly.

**What is *not* covered by any color slot**: Filament's "raised surface" chrome consistently uses
literal `bg-white ... dark:bg-gray-900` (not `bg-gray-white` or any custom-scale reference) across
essentially every card-like component:

| Surface | Class | Template |
|---|---|---|
| Sidebar | `.fi-sidebar` | `filament/resources/views/components/sidebar/index.blade.php` |
| Sidebar header | `.fi-sidebar-header` | same file |
| Topbar | `.fi-topbar nav` | `filament/resources/views/components/topbar/index.blade.php` |
| Section/card | `.fi-section` | `support/resources/views/components/section/index.blade.php` |
| Stat widget card | `.fi-wi-stats-overview-stat` | `widgets/resources/views/stats-overview-widget/stat.blade.php` |
| Table row | `.fi-ta-record` | `tables/resources/views/index.blade.php` |

Since `white` and `gray-900` are Tailwind's literal palette, not Filament's re-themable custom
scale, no amount of `$panel->colors()` registration touches them. Override directly in
`theme.css`, bundled since they share the identical pattern:

```css
.fi-sidebar,
.fi-sidebar-header,
.fi-topbar nav,
.fi-section,
.fi-wi-stats-overview-stat,
.fi-ta-record,
.fi-modal-window,
.fi-dropdown-panel {
    background: var(--rl-raised-surface) !important;
}
```

`!important` is required here — these are real Tailwind utility classes with normal specificity,
so a plain override loses without it. This is a legitimate use of `!important` (a documented
Filament customization point via the theme CSS layer), not a specificity hack to avoid.

Don't try to enumerate every remaining `bg-white`/`text-white` occurrence (buttons, badges,
tooltips, dropdown items) — most of those are deliberately staying white/near-white for contrast
reasons (e.g. white text on a colored primary button) and blanket-redefining Tailwind's `white`
token in `tailwind.config.js` risks breaking exactly that contrast. Cover the handful of large
chrome surfaces above; leave small interactive elements on Filament's defaults.

## Brand name

```php
->brandName('Homelab Dashboard')
```

Replaces the "Laravel" default shown via `<x-filament-panels::logo>` (class `.fi-logo`) in the
sidebar header and login page. Plain string, no HTML escaping concerns unless passing an
`Htmlable`/closure. If the theme's CSS already applies `text-transform: uppercase` to `.fi-logo`
(a common "eyebrow label" treatment), pass normal title case here — the casing transform is
presentation, not data.

## Verification

`@filamentStyles`/`@filamentScripts` and a panel's `->theme()`/`->font()` links all render as
real `<link>`/`<style>` tags in the response body — but a naive single-line regex/grep for
`<link[^>]*>` can miss them if Filament wraps the tag across multiple lines. Search for the
asset filename substring instead (`grep -o 'forms.css\|theme.css'`) when confirming a stylesheet
is actually being requested, and always confirm final rendering with a real browser (Playwright
screenshot, both light and dark via `localStorage.setItem('theme', 'dark')` + reload — Filament's
dark mode is a `.dark` class toggle on `<html>`, not a `prefers-color-scheme` media query, so
`theme.css` dark overrides must use a `.dark { ... }` selector, not
`@media (prefers-color-scheme: dark)`) — curl alone cannot catch mixed-content blocking or actual
visual regressions.

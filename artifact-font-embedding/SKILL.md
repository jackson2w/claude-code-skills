---
name: artifact-font-embedding
description: This skill should be used when the user asks to "show me font pairing options", "preview typography choices", "compare fonts", "mock up different fonts", or asks to see design/typography options rendered with real fonts inside a Claude Artifact. Also applies whenever a Worker/Artifact needs a Google Font and the CSP blocks external font requests. Covers sourcing real font files via Fontsource and embedding them as base64 @font-face data URIs so an Artifact renders the actual typeface rather than silently falling back to a system font.
version: 0.1.0
---

# Embedding real fonts in Artifacts

Claude Artifacts run under a strict CSP that blocks requests to any external
host — including a `<link>` to Google Fonts or any other font CDN. Linking
one anyway doesn't error visibly; it silently falls back to the next font in
the stack, and the artifact looks like it's using the right typeface when it
isn't. The only reliable way to show a *real* typeface inside an Artifact is
to inline the font file itself as a base64 `@font-face` data URI.

This matters most for font-pairing comparisons ("show me 5 options for this
site's typography") and any other design mockup where the actual letterforms
are the point — a system-font fallback defeats the purpose of the preview.

## Core workflow

1. **Source the real font files via [Fontsource](https://fontsource.org/)**,
   not by hand-downloading from Google Fonts. Fontsource packages the entire
   Google Fonts catalog (plus some others) as npm packages built for
   self-hosting — this is the fastest way to get a real `.woff2` file for any
   named typeface.

   ```bash
   mkdir -p /tmp/font-scratch && cd /tmp/font-scratch
   npm init -y >/dev/null 2>&1
   npm install @fontsource-variable/fraunces @fontsource-variable/inter
   # Static (non-variable) families use the plain package instead:
   npm install @fontsource/libre-caslon-display
   ```

   Prefer the `@fontsource-variable/*` package when one exists (most popular
   families have one) — a single file covers the whole weight range instead
   of needing one static file per weight.

2. **Locate the needed file(s)** under `node_modules/@fontsource*/<name>/files/`.
   File names encode subset, axis, and style, e.g.
   `fraunces-latin-wght-normal.woff2` (variable, weight axis, upright) or
   `fraunces-latin-wght-italic.woff2` (italic). For a Latin-script preview,
   the `-latin-` (not `-latin-ext-`) file is almost always the right one —
   see `references/fontsource-cheatsheet.md` for the full naming pattern and
   how to confirm a family's actual variable axes before writing `@font-face`.

3. **Write a Node build script that reads and base64-encodes each file, then
   injects it into an HTML template — do not inline base64 by hand in a Write
   call.** A single variable font file is tens of KB; base64-encoding inflates
   that further, and typing or reasoning over that text directly burns
   context for no benefit. Let a script do it and write the assembled output
   straight to disk. Template in `scripts/build-font-preview.js` — copy it,
   adjust the `FONTS` list and the HTML/CSS content, run `node build.js`.

4. **Validate the generated file before publishing** — the template-literal
   nesting (CSS inside a JS template string, itself containing `${...}`
   interpolations) is easy to get subtly wrong:

   ```bash
   grep -c '${' output.html   # should print 0 — any hit means an interpolation leaked through unescaped
   python3 -c "import re; html=open('output.html').read(); \
     [print(t, 'MISMATCH') for t in ['div','section','span','p'] \
      if len(re.findall(f'<{t}(?:\\\\s[^>]*)?>', html)) != len(re.findall(f'</{t}>', html))]"
   ```

5. **Publish with the Artifact tool.** Pick a favicon emoji and keep it
   stable across redeploys of the same comparison (redeploy to the same file
   path to update the same URL rather than minting a new one for every
   revision the user asks for).

## Design content, not just fonts

When building a font-pairing comparison, follow the `artifact-design` skill's
"build with real content" principle — reuse the actual site's real copy,
real album/page names, real color tokens, and real type-scale values (don't
invent a generic lorem-ipsum sample). Show the *current* setup as a baseline
section for direct comparison, not just the candidates in isolation. If the
site already has an established design system (colors, spacing tokens),
inherit it into the comparison page rather than picking new ones — the
comparison should isolate the font variable, not restyle everything at once.

## Performance context worth relaying to the user

If the underlying request is really "what fonts should I use on my
site" rather than just "show me a preview," mention that self-hosting via
Fontsource (or downloading the same files into the project's own assets) is
more performant than linking Google Fonts' CDN directly in production: the
Google Fonts CDN requires two extra cross-origin connections (the CSS host
and the font-file host), even with `preconnect` hints, and sends visitor
requests to Google. **[Bunny Fonts](https://fonts.bunny.net/)** is a
same-syntax, privacy-respecting drop-in replacement for the Google Fonts
`<link>` tag if the user doesn't want to vendor font files into their repo
but still wants better performance/privacy than Google's CDN directly.

## Additional resources

- **`references/fontsource-cheatsheet.md`** — package naming patterns,
  variable vs. static file naming, how to check a family's real weight/axis
  range, and common pitfalls (missing `format("woff2-variations")`, wrong
  subset file, italic-only families).
- **`scripts/build-font-preview.js`** — a copy-paste build-script skeleton:
  reads font files, base64-encodes them, injects into an HTML template, and
  writes the final artifact HTML to disk.

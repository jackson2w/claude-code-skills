# Fontsource cheatsheet

## Package naming

- Variable font (preferred, single file covers the weight range):
  `@fontsource-variable/<kebab-case-family-name>`
  e.g. `@fontsource-variable/inter`, `@fontsource-variable/fraunces`,
  `@fontsource-variable/space-grotesk`.
- Static font (fixed weights, one file per weight): `@fontsource/<name>`
  e.g. `@fontsource/libre-caslon-display` (this family only ships weight 400,
  no variable version exists).
- Not every family has a variable package — if
  `npm install @fontsource-variable/<name>` 404s, fall back to
  `@fontsource/<name>` and pick specific weight files instead.

## Finding the right file

Files live under `node_modules/<package>/files/`. Naming pattern:

```
<family>-<subset>-<weight-or-axis>-<style>.woff2
```

- `<subset>`: `latin` (plain Latin) vs `latin-ext` (adds accented
  characters for European languages) — for English-only preview content,
  use the plain `latin` file, it's smaller and sufficient.
- `<weight-or-axis>`: for variable packages, this is literally `wght` (the
  weight axis) — one file, `font-weight: <min> <max>` covers the whole
  range in `@font-face`. For static packages, this is a number (`400`,
  `700`, etc.) — one file per weight actually needed.
- `<style>`: `normal` or `italic`. A family with both upright and italic
  needs two separate `@font-face` blocks (two files), sharing the same
  `font-family` name — the browser picks the right file based on
  `font-style` in the rule that matches how it's used in CSS.

List a package's available files directly rather than guessing:

```bash
ls node_modules/@fontsource-variable/<name>/files/ | grep latin-wght-normal
ls node_modules/@fontsource-variable/<name>/files/ | grep latin-wght-italic
```

## `@font-face` for a variable font

```css
@font-face {
  font-family: "Fraunces Preview";
  src: url(data:font/woff2;base64,<BASE64>) format("woff2-variations");
  font-weight: 300 900;   /* the family's real min/max — check, don't guess */
  font-style: normal;
  font-display: swap;
}
```

Using plain `format("woff2")` for a variable file still often works in
modern browsers, but `format("woff2-variations")` is the correct, explicit
hint and avoids ambiguity in stricter engines.

## `@font-face` for a static font

```css
@font-face {
  font-family: "Libre Caslon Display Preview";
  src: url(data:font/woff2;base64,<BASE64>) format("woff2");
  font-weight: 400;   /* exactly the one weight this family ships */
  font-style: normal;
  font-display: swap;
}
```

## Common pitfalls

- **Wrong axis range**: don't write `font-weight: 100 900` for a family that
  only actually spans e.g. 300–900 — check the family's real range (Fontsource's
  own site page for the family lists it, or inspect the file's own metadata
  if uncertain) so browsers don't clamp/guess incorrectly at the extremes.
- **Forgetting the italic file**: if the design calls for an italic display
  face (e.g. a "literary" or "handwritten" treatment), the upright-only file
  won't have real italic glyphs — browsers will *synthesize* a slant on the
  upright face, which looks noticeably worse than a real italic cut. Grab
  the `-italic` file explicitly.
- **Subsetting too aggressively**: the `latin` subset drops characters like
  em dashes' typographic cousins in some fonts or extended punctuation in
  rare cases — if the preview copy uses unusual glyphs, sanity-check they're
  covered, or fall back to `latin-ext`.
- **Payload creep**: embedding many full families for a 5-way comparison adds
  up (typically tens of KB each after base64 inflation ~33%). Fine for a
  one-off comparison artifact; not something to embed this way in a
  production page — that's what self-hosting the *chosen* one or two fonts
  as real assets (not base64) is for.

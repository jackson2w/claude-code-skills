---
name: website-design-references
description: >-
  Will's reference sites for the websites he has Claude build: what he likes about each, with the
  exact fonts, sizes, colours, spacing and interaction details measured from the live site, so a
  new site can start from proven choices instead of a fresh guess. Starts with neverenough.com
  (Andrew Wilkinson's essay site: warm paper and ink, three-serif-family editorial typography,
  62ch measure, drop cap, small-caps eyebrows, paper grain, ink-wipe buttons). Use when building
  or redesigning any website, blog, essay or long-form reading page, personal site, landing page
  or newsletter page for Will. Also paulstamatiou.com (light/dark toggle with a circular
  reveal, sun/moon icon morph, and a catalogue of small animations for a flourish pass). Trigger phrases include "build me a website", "new site",
  "personal site", "blog design", "essay page", "make it look like neverenough", "editorial
  typography", "reading experience", "the look I like", "design reference", "dark mode toggle", "light mode",
  "theme switch", "paulstamatiou", "flourishes", "micro-interactions".
---

# Website design references

Sites Will has pointed at and said "I like this". Each entry records **what he named** and
**measured values** (pulled from the live CSS, not eyeballed). Use them as the starting point for a
new site; don't copy a site's identity (name, logo, signature, colours as a set), borrow its
decisions.

**Will's rules win over any reference site.** Load `website-building-preferences` first; where a reference uses something its §7 bans (cream paper with warm accents, small-caps eyebrow labels, decorative numbering), take the craft, not the pattern.

When Will names a new reference site, analyse it the same way (fetch the HTML and the CSS bundle,
read `@font-face`, `:root`/theme variables and the article markup) and add an entry here.

## neverenough.com (added 2026-10-23)

Andrew Wilkinson's essay/newsletter/book site. Will: "I like the typography, the layout, the
simplicity." Reference page: `/essays/i-got-diagnosed-with-a-brain-disorder`.

**Platform:** Next.js (App Router, Turbopack build, `next/font`, `next/image`, generated
`opengraph-image` per essay) on **Vercel**, styled with **Tailwind CSS v4**. No headless CMS is
visible, and images are served from the site's own `/photos/`, so the essays most likely live in
the repo as Markdown/MDX. GTM for analytics. For Will's sites the equivalent is a static build
(11ty or Astro) on **Cloudflare Pages**: nothing on this site needs a server.

### Typography: three families, each with one job
| Role | Font | Used for |
|---|---|---|
| Display | **Newsreader** (variable, opsz, italic) | headlines, h2/h3, pull quotes, wordmark, eyebrows, drop cap |
| Text | **Source Serif 4** (variable) | body copy, card blurbs, form inputs |
| UI | **Inter Tight** | nav, buttons, read-time/date meta |
| Labels | **JetBrains Mono** | breadcrumbs, card meta (`2 MIN · APRIL 29, 2026`), signature line |

All free on Google Fonts. Fallback stacks name the premium faces they stand in for
(`"GT Sectra", "Tiempos Headline"` / `"Tiempos Text"`), so the design intent is
Tiempos-style editorial.

- Body: **1.1875rem (19px), line-height 1.7, max-width 62ch**, paragraphs `mb-7`. Site-wide base 1.125rem / 1.6667.
- H1: 2.25 → 2.75 → 3.25 → 3.5rem across breakpoints, **leading 1.04, tracking -0.018em**; one word set in *italic* for voice ("I *got* diagnosed…").
- H2: 1.75–2rem, leading 1.18, tracking -0.012em, `mt-14 mb-5`. H3: 1.375rem **italic** display.
- Blockquote: display italic 1.5–1.75rem, centred, max 52ch, in the accent blue.
- **Drop cap** on the first paragraph: display face, 4.6em, weight 500, accent colour, floated; first paragraph slightly larger (1.21rem).
- **Eyebrow** labels: display face in **true small caps** (`font-variant-caps: all-small-caps`, `smcp`/`c2sc`), 0.9375rem, +0.05em, soft ink.
- Mono labels: 0.6875rem, uppercase, **tracking 0.14–0.16em**.
- `text-wrap: balance` on headings/eyebrows, `pretty` on body; `hanging-punctuation: first last allow-end`; `font-feature-settings: "kern","liga","calt"`; `text-rendering: optimizeLegibility`.
- Header wordmark uses `font-variation-settings: 'opsz' 36`, i.e. the optical size axis is used on purpose.

### Colour: paper and ink, light + dark
| Token | Light | Dark |
|---|---|---|
| paper (bg) | `#f4eee2` | `#17130f` |
| paper-deep (code, wells) | `#ebe3d3` | `#211a14` |
| paper-shadow (rules, borders) | `#d9cfb8` | `#3a3026` |
| ink (text) | `#1c1b18` | `#f1e7d5` |
| ink-soft (meta) | `#5a554b` | `#b9ab95` |
| signature (links, drop cap, quotes) | `#2b4570` | `#9fb8ee` |
| coffee (hover, focus) | `#1f4ea8` | `#d99a56` |
| margin (red-pen accent) | `#b8361f` | `#e46d55` |

Warm off-white and near-black, never pure `#fff`/`#000`. One cool accent (fountain-pen blue) for
links, plus a hover colour. Dark mode is a `html.dark` class toggle (sun/moon button in the
header). `::selection` is accent-on-paper.

### Layout
- Sticky header: `bg-paper/88` + `backdrop-blur-sm` + hairline bottom rule; wordmark left, 6 small sans nav links centred, theme toggle, then a black **Subscribe** button. Mobile collapses nav into a menu button; tap targets 44px (`h-11`).
- Article: breadcrumb (mono) → eyebrow category → H1 → `10 min read · March 12, 2025` with a hairline under it → body.
- Body column 62ch; from `xl`, an **18rem sticky right rail** ("Filed under" categories). Plenty of side margin otherwise.
- Ending: handwritten **signature image** + mono line `Andrew · Victoria · March 12, 2025`; then "Read next" (3 cards, top hairline, mono meta, display title, serif blurb, "Read →"); then a book promo; then "Keep reading".
- Sections separated by **hairline rules** (`border-paper-shadow/60`) and big vertical gaps (`mt-20`), never boxes or shadows. Radius is tiny (2–3px) everywhere.
- In-article newsletter form: italic display line ("I send one of these roughly monthly. About 30,000 people read it.") + email + button.

### Texture and motion (subtle, all disabled by `prefers-reduced-motion`)
- **Paper grain:** a fixed `body::before` with an inline SVG `feTurbulence` noise at **4.5% opacity**, `mix-blend-mode: multiply` (screen, 3.5% in dark), drifting slowly (32s).
- **Ink-wipe button** (`.btn-ink`): ink background; a coffee-coloured `::before` scales in from the left on hover (`scaleX`, 0.42s `cubic-bezier(.77,0,.175,1)`), quicker out.
- Links: accent colour, **1px underline at 40% opacity, offset 3px**, turning to the hover colour.
- Page-load "veil" fade, headline lines rising in with a 3px blur, drop cap scaling in, pull quotes sliding in on scroll; book cover floats gently. One shared easing `--ease-ink: cubic-bezier(.22,.61,.36,1)`.
- Subscribe button pulses every 7s (pauses on hover). Use sparingly; it's the one attention-seeking thing on the page.

### What to take, in order of value
1. The three-serif-family split (display / text / UI sans) with mono for metadata.
2. 19px / 1.7 / 62ch body, tight-leading big display headlines.
3. Warm paper + ink palette with one blue accent, and a real dark mode.
4. Small-caps eyebrows, drop cap, italic voice words, hairline rules instead of boxes.
5. Grain and ink-wipe hover, only if the site is a reading site; skip the pulse and load animations for tools/dashboards.


## Abernathy "Broadside" (2026-11-04): the Black press, from sources

Will picked this direction for abernathymagazine.com. Source facts (Wikipedia, MFA Boston, Fonts In Use,
People's Graphic Design Archive): Emory Douglas art-directed *The Black Panther* newspaper (1967 to about 1980),
covers in **black plus one colour** with high-contrast photographs, laid out by **cut-and-paste** with rub-down type.
What the mockup took from it: hard offset "paste-up" shadows (no blur) cycling red/ink/green; one duotone (grey
photo multiplied onto red) for the lead; a newspaper dateline between a 4px and a 1px rule; section heads as ink
banners with a swallowtail notch (`clip-path`); a tilted rubber-stamp caption with a dashed inner outline; the
wordmark printed slightly off-register (`text-shadow: .035em .025em 0 red`); a 5px double-rule box for curated
lists. Other directions mocked and not picked: Margins (Paris Review / Tufte: book spine, ribbon, contents page)
and Full Bleed (Businessweek / NYT Magazine / The Pudding: colour fields, duotones that return to colour on hover).

## paulstamatiou.com (added 2026-11-18)

Paul Stamatiou's personal site (Head of Design at Sesame). Will: build a light/dark toggle like his, and **catalogue
his small animations and interactions for a "tweaks, adjustments and flourishes" pass on williejackson.com before it
goes live**. Measured from the live site 2026-11-18 (HTML, `/assets/globals-*.css`, the JS bundle, Playwright on dev).
Stack for context: a React SPA (TanStack Router, Tailwind v4, framer-motion), so client-side page changes.

### The theme toggle (built for williejackson.com 2026-11-18, mockups; see its CSS/JS comments)
- **Before paint:** an inline `<head>` script reads cookie `app-theme=light|dark`; with no cookie it follows
  `prefers-color-scheme` *and keeps listening* for system changes. Sets `html[data-theme]` and inline `color-scheme`.
  Cookie (not localStorage) because his pages render on the server.
- **One button, two states** (no "system" option in the UI). From "system" a press goes to the opposite of the current
  system mode. Generic label "Toggle light or dark theme". Button: 32px, 70% opacity → full on hover, `hover:scale-105`.
- **Icon morph (the classic sun/moon mask trick):** one disc masked by a second circle (`moon-cradle`) that sits outside
  in light and slides across in dark (`translate(20px,-20px)` → `(-5px,2px)`, 0.4s `cubic-bezier(.4,0,.2,1)`), carving a
  crescent; the disc scales 1.5×; the rays fade, scale 0.8 and turn half a revolution (0.5s). Shows the current mode.
- **Page change:** `document.startViewTransition`; `::view-transition-new(root)` gets a **feathered circular mask** (an
  SVG data-URI circle with `feGaussianBlur`), mask-size 0 → 10× the viewport over 800ms from the button's centre; old
  snapshot stays still underneath. Skipped under reduced motion or without VT support.
- **Afterglow:** 200ms after a change he sets `html[data-theme-changed]` for 4s, which runs an 11s **shimmer along the
  borders** of his content containers (a moving gradient on a masked 3px border, fading in and out). Subtle "the
  lights changed" acknowledgement. Not copied yet: candidate for the flourish pass.

### Palette character
- **Tinted, not neutral, in both modes:** light is a warm off-white with olive ink; dark is a deep green-black
  (`--color-body: oklch(18.5% .1 120)`). Selection colour tinted to match (`oklch(25% .075 145)` bg, `85% .1 145` text);
  `-webkit-tap-highlight-color` tinted too. Text shadow `0 1px 0` white at 75% on light-mode titles (a letterpress lift).

### Motion and interaction catalogue (candidates for the williejackson.com flourish pass)
Durations cluster at **150ms (colour), 200–300ms (UI), 450–500ms (reveals)**; easings `cubic-bezier(.4,0,.2,1)` and
`(0,0,.2,1)`; big entrances `cubic-bezier(.22,1,.36,1)`. Reduced motion turns nav transitions off entirely.
1. **Icon rail nav** (desktop, left): icons at 85% scale grow to 100% on hover; the label slides in from 5px left with
   opacity (300ms). Current page = white squircle chip with a soft shadow. `corner-shape: squircle` wherever supported.
2. **Links:** 2px underline offset 2px, decoration at 30% opacity → 50% and text colour shift on hover (150ms).
3. **Post table of contents as a "minimap" rail** (fixed, right edge, vertically centred): one short tick per heading,
   ticks sized to the section, the current one darker (`aria-current="location"`); fades and slides in (8px, 300ms)
   once you scroll past the intro; hover shows the heading name. Plus an inline TOC block at the top of long posts.
4. **Footnote previews:** hovering a footnote number opens a 22rem tooltip card with the note (clamped to 10 lines) and
   a "jump to footnote" button; it fades and nudges in (150ms). Positions above/below as space allows.
5. **Heading anchors:** a "#" appears in the margin on heading hover; clicking copies/links the section.
6. **Photo sets:** horizontal carousels with prev/next arrows, an "n/6" counter and the caption beneath; buttons in a
   frosted "liquid glass" style over photos.
7. **Lightbox:** black field, image scales up from its spot (420ms `cubic-bezier(.22,1,.36,1)`), backdrop fades
   (300ms), zoom button, arrows, count + caption chip, URL hash per photo (`#photo-<name>`) so a photo is linkable.
8. **Photo grid cards:** title rises from `translate-y-4` and a small label fades in from blur (filter + opacity +
   transform, 450ms) on hover.
9. **Gear cards:** a rounded plate fades in *behind* the item on hover (`::before` opacity, 300ms), not a scale.
10. **Posts/Favorites tabs** with an underline on the active tab; a live filter input over the posts list.
11. **Tap feel on phones:** `touch-action: manipulation`, tinted tap highlight, slightly darker pressed state.
12. Small polish: `text-wrap: balance` on titles and intros, `scrollbar-gutter: stable`, `overscroll-behavior: contain`
    on popovers, speculation-rules prerender (Cloudflare `Speculation-Rules` header).

### The photostream (`/photostream`, `/photo/<id>`; measured 2026-11-19 for photos.jackson2w.com)
Will asked for this rebuilt as photos.jackson2w.com (decisions: memory `project_photo_site_photostream`).
- **Grid:** pure black, full bleed, 4px gutters, **masonry (shortest column), uncropped**, newest first. Columns
  1 / 2 ≥640 / 3 ≥1024 / 4 ≥1800. Positions are computed at render and written as CSS custom properties in `cqw`
  units per breakpoint (`--pf-t2`, `--pf-l2`, `--pf-hgt2`, grid height as `max()` of per-column sums) on an
  `@container`, so there's no JS layout and no CLS. Each `<img>` carries a 24×16 WebP LQIP as an inline
  background-image. No captions, no hover effect in the grid. 30 cards per page, IntersectionObserver loads more.
- **Header:** two frosted "liquid glass" pills, fixed: back arrow (40px circle) top-left, centred title pill.
  Glass = `rgba(0,0,0,.28)` + `backdrop-filter: blur(14px) saturate(150%)` + a 135° white sheen gradient + inset
  1px highlights + `0 4px 14px -6px` drop. Title pill opens an **about card**; the feed **recedes** behind it
  (scale .95, radius ~22px, `.39s cubic-bezier(.23,.88,.26,.92)`, iOS-sheet feel), the card scales in from 1.1.
- **Open a photo:** the tile grows from its grid rect to the full-screen fit (`.42s cubic-bezier(.22,1,.36,1)`);
  back reverses into the tile. Photo pages are a horizontal pager with neighbours preloaded; drag with pointer
  events, commit at 50% width or 400px/s flick, spring (damping 38, stiffness 420); `touch-action: pinch-zoom`.
  Keys: ←/↑ newer, →/↓ older, Esc back to the grid. Pages more photos in when within 20 of either end.
- **Details pill:** monospace date ("Sep 10th") + chevron; expands (grid-rows 0fr→1fr, chevron flips with an
  overshoot `cubic-bezier(.3,1.18,.6,1)` 360ms) into a glass card: caption (markdown-lite: links, bold, italic),
  rule, then camera (→ gear page), lens, place (→ place stream), each row blurring in (`blur(5px)`, opacity 0,
  `translateY(-4px)`) staggered. No exposure values, no download, no share.
- **Routes:** `/photostream/<place>` is a filtered stream with its own title/OG. OG image is a 1600px JPEG.
- Stack: React SSR (TanStack), images through Cloudflare `cdn-cgi/image` widths 480–3000, `format=auto`,
  `metadata=none`. A static 11ty build reproduces all of it: build-time masonry, cross-document View Transitions
  for the grow, vanilla pointer-event pager.

### What to take for williejackson.com, in order of value
1. The toggle (done). 2. Footnote previews, if posts get footnotes. 3. A heading minimap rail on long posts and the
speaking page. 4. Lightbox polish: grow-from-thumbnail, linkable photo hash. 5. The post-toggle border shimmer, kept
very quiet. 6. Heading anchors. Skip his icon rail (Will's nav is text) and anything that is image hover zoom (banned).


## What reads as AI-made, and darkroom references (researched 2026-11-19 for the williejackson.com flourish pass)
- **Published "AI tell" lists to check proposals against:** Anthropic's frontend-design skill
  (github.com/anthropics/skills, skills/frontend-design): fade-and-slide-up entrances on every section, hover
  transitions on every card, tinted near-black + one accent + mono data labels ("template chrome"), all-caps eyebrows,
  "→" on links; its advice is "one orchestrated moment" drawn from the subject's own materials. impeccable.style/slop:
  pulsing dots, marquees, bounce easing, radial halos/soft spotlights, glowing accents on dark mode, gradient text,
  italic serif display headlines. OpenAI's GPT-5.4 frontend guide: no cards by default, in-situ photography, 2–3
  intentional motions. A dark + gold + mono site sits near these clusters, so distinctiveness has to come from the
  site's own metaphor (for Darkroom: developing prints, safelight, enlarger, contact sheets), not more palette.
- **jasonbergh.com** (Blacklead Studio; Codrops 2026-02-20): the closest "darkroom" relative: film-edge lines that
  persist across pages via sessionStorage, stepped moving grain (noise PNG, color-dodge), video grows from the click
  point, effects cut back on slow connections.
- **paco.me:** several noise SVGs at different baseFrequency (0.75 grain, 0.05 paper mottle); progressive blur.
- **Shadows:** joshwcomeau.com/css/designing-shadows: one light source, same x:y ratio, layered, tinted to the
  background hue. Never animate letter-spacing in an entrance (it reflows: CLS).
- **CSP note:** strict style-src blocks style attributes but not CSSOM (`el.style.setProperty`), so pointer-driven
  custom properties and per-navigation `viewTransitionName` (pageswap/pagereveal) need no generated classes.

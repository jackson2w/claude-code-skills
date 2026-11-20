---
name: website-building-preferences
description: >-
  Will's standing rules for every website Claude builds for him (written with Claude chat, adopted
  2026-10-23): GRT-first typography via grt.py, OKLCH palettes proposed as 2-3 options, no AI-slop
  defaults, hand-written CSS + vanilla JS + Eleventy, self-hosted fonts, Playwright screenshot loop,
  Cloudflare Pages via dashboard Git integration, WordPress-to-11ty migration rules, per-project
  notes (williejackson.com, abernathymagazine.com, photos.jackson2w.com). Load BEFORE any website,
  landing page, redesign, migration, 11ty, GRT, typography, palette or Cloudflare Pages work for Will.
  Trigger phrases: "build me a website", "new site", "landing page", "redesign", "migrate from
  WordPress", "11ty", "eleventy", "golden ratio typography", "GRT", "grt.py", "palette", "font pairing",
  "open graph", "og:image", "social preview", "lighthouse", "security headers", "CSP", "robots.txt",
  "favicon", "structured data", "llms.txt", "specification.website", "site audit", "launch checklist".
---

# Website-building preferences (Will)

## Local notes (read first; these amend the document below)

- **Caching is off until each site's launch (Will, 2026-10-23; refined 2026-11-05).** Mockups and previews stay
  uncached so changes show up at once. The starter's generated `_headers` turns immutable caching on when
  `site.launched` is true, with CSS fingerprinted by the `fp` filter (§10, §15). Security headers on `/*` are always on.
- **Install:** this file is the global copy (synced via the skills repo). `grt.py` lives next to it and
  is symlinked at `~/.claude/tools/grt.py`. Each site repo also carries a `CLAUDE.md` with its own
  §13 entry; the repo file wins.
- **grt.py v2 (2026-10-23, Will approved the fix).** Rebuilt on the calculator's published equation
  (grtcalculator.com/math/): `h = f·[(3−φ) + (2φ−3)·w/(34f) + c]`, `c = (x − (φ−1))/φ`, with sizes rounded
  to whole px before their line heights and spacing chain-rounded, exactly as the calculator does.
  `--self-test` replays **168 stored calculator answers** (6 fonts × 7 sizes × 4 widths) and matches all of
  them. Output is rem plus Utopia-style fluid `--grt-step-N` / `--grt-step-lh-N`; no border-left quotes.
  v1 ran heading line heights 4–8% tight.
- **x-height means x-height ÷ CAP height** in GRT. §3's `--x-height 0.49`-style values are x-height ÷ em and
  give wrong line heights; v2 refuses `--x-height` and takes `--font-file <ttf/otf>` (reads OS/2) or
  `--x-ratio`. File-measured ratios can differ slightly from the calculator's browser-measured ones
  (Source Serif 4 0.709 vs 0.736, ≤1 px difference); the calculator applies no correction at all for fonts it
  has no data for (Inter: implied 0.618). Prefer the font file: it's reproducible for any face.
- **Preview deploys:** throwaway mockups go to the Direct Upload project `wj-site-mockups` (wj-site-mockups.pages.dev) with `CF_PAGES_TOKEN` (Infisical homelab-fleet/dev, Pages Write, Will 2026-10-23). Create new Pages projects via the API, not `wrangler pages project create` (see cloudflare-pages-gotchas). Never touch the live `j2wtalent` Pages project from a mockup.
- **Screenshot gotcha (2026-11-04):** Playwright `fullPage` clip screenshots render `mix-blend-mode` images (duotones) blank, so a correct page looks broken. Use scroll-and-capture viewport shots instead (`~/projects/sites/mockups/scripts/dev/vslice.mjs`). The dev box has no sharp/ImageMagick; resize images through Chromium canvas (`scripts/dev/batch-resize.mjs`).
- **Mining a WordPress site for a redesign:** the public REST API (`/wp-json/wp/v2/posts|categories|tags|users|media`, `per_page=100`, `_fields=`) gives every post, author bio, taxonomy and featured-image size without admin access. Nested `_fields` like `media_details.width` silently return nothing with `include=`; ask for `media_details` whole.
- **Clamped summaries cut words in half (Abernathy, 2026-11-06).** `-webkit-line-clamp` puts its "…" by trimming
  characters, so "marching from" can show as "marching fro…". Fix it at build: a summary is leading whole sentences up to
  N characters (an abbreviation never ends a sentence), a too-long first sentence is cut between words with "…", and N
  comes from measuring each clamp's capacity at every width (`scripts/dev/clamp-capacity.mjs` in the mockups repo). Keep
  the clamp only as a safety net sized never to fire, and prove it with `checks.mjs` (0 clamped). Will chose this.
- **Tap-area padding moves `border-bottom` underlines (2026-11-06).** `padding-block` on an inline link enlarges the hit
  area without moving text, but a `border-bottom` "underline" moves down with the padding (Abernathy's byline rule landed on
  the date line below; Will caught it on his phone). Pad only links underlined with `text-decoration`. Any fix applied
  to a list of selectors needs a phone screenshot of each selector, not just a passing measurement.
- **Alternating bands (corrected 2026-11-07):** with a cream page header AND a fixed-colour closing band, two colours
  cannot alternate at both ends when the band count is even; counting from the end only moved the clash to the top
  (header + first band merged on About, Contributors, Archive). Will's rule: count from the top,
  `main > .band:nth-child(odd of .band)` = paper (`of S` ignores stray `<script>`s), and let the closing band take
  whichever colour comes next. Verify with a script that every page has no two same-colour neighbours, header included.
- **WordPress migration: excerpts are content too.** Calls to action stripped from post bodies survive in WP excerpts
  ("please submit your article here", "Subscribe via email"), and so do display-name quirks ("willie jackson") and
  straight quotes in names. Run the same cleanup on excerpts, names and any summary field, then grep the built site.
- **Consistency-pass toolkit:** `~/projects/sites/mockups/scripts/dev/` (README): pass-measure + pass-analyze.py,
  checks, bands, hit-test, byline-gap, tall-check, pass-probe-rows, clamp-capacity, shots. The README lists the known,
  accepted flags (tilted prints read as spills, optical -0.03em title offsets, display sizes off the step scale) so a
  pass doesn't re-chase them. Run against a branch preview (`--branch pass2`), then promote.
- **Measurement misses collisions between elements (2026-11-07).** pass-measure checks each element against its
  container, not against its neighbours: twice Will found, on his phone, a byline divider touching the red name
  underline above it (an inline-block's `border-left` is as tall as the whole line box). When a layout stacks a
  divider under an underline, measure the gap (`byline-gap.mjs`); give the divider a text-height line box.
- **Meta descriptions: measure pixels, not characters (2026-11-20).** Google cuts the desktop snippet at about
  920px of 14px Arial, so "≤160 characters" is not enough: williejackson.com's 160-char home description measured
  1,009px and Will saw it cut off ("…communication drive"). Measure with a canvas `measureText` at `14px Arial` and
  keep each description ≤ ~900px (often 130-145 characters), with the key words first. Re-check post descriptions
  that were only trimmed to ≤160.
- **Images bigger than the text column under a strict CSP (2026-11-07).** To break a photo out to a wider sibling's
  width, make the wide parent a size container (`container-type: inline-size`) and use `100cqw` with a negative
  margin of `(100% - 100cqw) / 2`; verify the edges equal the sibling's. A frame sized from the photo (`fit-content`,
  `width: auto` + `max-height`) collapses to 0 until a lazy image loads, and `style=""` is banned by the CSP: emit a
  shape class per photo (`r-WxH`) from the build into a generated stylesheet that sets `--r`, and size the frame from it.
- **WordPress images: the displayed file is not the original.** Posts often show an edited `-e<timestamp>` or `-WxH`
  copy (701px) while the upload behind it is 2048px; request the base filename and read `media_details` before
  deciding a photo "can't be bigger". Some uploads really are small: search the media library before asking the owner.
- **schema.org (researched 2026-11-07 for Abernathy; Will chose "do it all"):** worth doing as correctness, not as an AI trick. Google's May 2026 AI-features guide: no special markup for AI Overviews/AI Mode, keep it for rich results. Bing says schema helps Copilot; ChatGPT/Perplexity tests mostly read visible text, so never put a fact only in JSON-LD. Do: build BreadcrumbList from the SAME data as the visible trail (mismatches crept in on 4 page types); author pages = ProfilePage whose Person `@id` the Article.author points at; zoned datePublished/dateModified; Organization full record on home/About only; WebSite alternateName for site names; robots `max-image-preview:large` for Discover. Skip: VideoObject without a watch page, Event for past events, FAQ/QAPage for interviews, SearchAction (sitelinks search box gone), Speakable. Check every page on every build (mockups `scripts/abernathy-check-jsonld.py`); `validator.schema.org/validate` takes a POSTed `url=` for spot checks. `breadcrumb` is a WebPage property: on a BlogPosting/Article the validator warns, so give the post a WebPage node (mainEntity → the post) that carries it. The validator is Google-hosted and starts answering with a "sorry" 302 captcha after ~15 quick POSTs; space spot checks out.
- **Agent readiness (isitagentready.com, williejackson.com 2026-11-18, Will: "resolve everything you can").** Scan with
  `curl -X POST https://isitagentready.com/api/scan -d '{"url":…}' -H content-type:application/json` (full check list:
  its `/llms-full.txt`). Level 4 of 5 is the honest ceiling for a content site: robots `Content-Signal` (ai-train is
  the owner's call: ask), sitemap, RFC 8288 `Link` headers on `/` (describedby → llms.txt and the skills index,
  alternate → index.md), Markdown negotiation, an Agent Skills index (a real skill, e.g. "how to book him"), an ARD
  `/.well-known/ai-catalog.json`. Cloudflare's own Markdown for Agents needs a Pro zone; on Free use the Pages
  `_worker.js` + build-time `index.md` twins in the mockups repo's `scripts/agent/` (reuse it), with `_routes.json`
  excluding assets and the project set to fail open. Don't fake MCP server cards, A2A cards, API catalogs, OAuth
  metadata or DNS-AID records for a site with no API, login or agent. WebMCP: declarative `toolname`/`tooldescription`
  on existing forms; `toolautosubmit` only on read-only ones (search).
  **Parity is part of the job (Will):** agent files must never say what the pages don't. Derive them from the built
  pages; mark any remaining fact `[[claim]]`; gate every build with `wj-agent-check.py` and verify the deployed copy with
  its `--served --settle 600` mode (Pages can serve stale per-URL copies for days and fresh deploys 404 at random edges
  for minutes). A deleted page may need a Worker 410 (`--gone`) to stop being served.
- **A whole-site import, learned on Abernathy (2026-11-07; how-to in that repo's CLAUDE.md):** (1) a `foo.json` beside
  `foo.js` in `_data/` shadows it under the same name (keep generated JSON outside `_data/`); (2) Eleventy adds only
  page 1 of a paginated template to collections unless `addAllPagesToCollections: true` (the sitemap silently listed 14
  of 280 pages); (3) Pages applies `_redirects` before serving files, so a pattern like `/:a/:b/` swallows real pages:
  list per-URL rules (2,000 static allowed), and placeholders are not substituted inside a query string; (4) a branch
  alias caches an old 301, so test redirects on the unique deployment URL; (5) prove every old URL with a resolver that
  mimics Pages (redirects, then files, then #fragments) against the WordPress sitemaps; (6) photo encoding is CPU-bound:
  shard it across idle machines (iMac, dfw) with matching sharp/libvips versions, then decode-check every file (killed
  encoders leave truncated files); commit derivatives, since a Pages build can't encode hundreds of photos in time.
- **Light/dark toggle on a strict-CSP static site (williejackson.com, 2026-11-18; code in mockups `src/js/theme-init.js`,
  `darkroom.js`, `w4.css`).** A tiny *blocking* `<script src>` at the top of `<head>` applies the saved choice before
  paint (the CSP allows no inline script; a hash also works). Tokens: dark on `:root`, the light set on
  `:root[data-theme="light"]`; give any part that must stay dark (a photo lightbox) the dark block too (`:root, .lightbox
  {…}`), so composite tokens recompute there. The reveal is a View Transition whose `::view-transition-new(root)` gets a
  `radial-gradient` mask animated with WAAPI from the button (an SVG data-URI mask would need `data:` in img-src). Turn off
  named view transitions during it (`.theme-vt * { view-transition-name: none !important }`) or those elements cross-fade
  outside the circle. Update `theme-color`/`color-scheme` metas, listen for `storage` so other tabs follow, honour reduced
  motion. Offer 2–3 light palettes in a trial bar and contrast-check each against page AND panel colours.
- **Two underlines on one link misalign (2026-11-18).** A link with a `text-decoration` underline plus a background-image
  hover line shows two lines on hover: the text underline sits at baseline + offset, the background line at the bottom
  of the inline box, and the gap grows with the font's descent (5px on a 42px display face). Draw both as background
  layers at one measured height (`background-position: 0 calc(100% - var(--ul-lift))`, lift measured per font by
  screenshot row-scan), and keep the resting position exactly where the old underline was.
- **Image search audit (2026-11-18, both sites).** Crawl the served site (every sitemap page) for: alt present and specific,
  width/height, AVIF/WebP with a JPEG `src` (the URL Google indexes), og:image + og:image:alt + twitter:image:alt, robots
  `max-image-preview:large` at launch (and no X-Robots-Tag noindex left on image files), and, in a real browser at phone and
  desktop width, any `loading="lazy"` image that is on screen at first paint (a hero-less post's lead photo is the usual
  case: make it eager). Article JSON-LD wants 16:9, 4:3 and 1:1 images (Google's Article guide): crop them at build from the
  original with the share image's focal point, never upscale, and look at every square on a contact sheet (about 1 in 30
  cut a face). Not worth doing: renaming image files, image sitemaps when every image is a plain `<img>`.
- Reference sites and measured values: `website-design-references` skill. Where a reference site
  uses something §7 bans (neverenough.com's cream paper, small-caps eyebrows), this document wins.

---

# Website-Building Preferences: Will Jackson

Global preferences for every website Will builds with you. Drop this in `~/.claude/CLAUDE.md` (global) or a repo root.
Precedence: a project's own `CLAUDE.md` > this file > your defaults. If an `AESTHETICS.md` exists alongside this file, read it before any design work.

Will's site entity name is **"Willie Jackson"** (structured data, author fields, copyright). In conversation he goes by Will.

---

- **A launch isn't done until the custom domain itself is audited (williejackson.com, 2026-11-18).** Every pre-launch
  check passed on pages.dev while, on the live domain, the zone's Rocket Loader stopped all site JavaScript under Trusted
  Types for ~50 minutes; Will's "now that it's live, run a complete audit" found it. Zone settings (Rocket Loader, Email
  Obfuscation, HTTPS rewrites, Browser Cache TTL, HSTS) act only on the custom domain. Right after a cutover, without being
  asked: (1) `live-vs-build.py` (every live page byte-for-byte against the build), (2) `live-console.mjs` (console errors
  and "did the page's own script run" at 1280 and 390), (3) `site-audit.py` on the live origin (it now fails on Cloudflare
  rewriting), (4) schema vocabulary, feed and old-URL sweeps. Two zone-only traps seen twice now (williejackson.com 11-18, j2wtalent.com 11-19):
  Email Address Obfuscation rewrites `mailto:` links and its decoder dies under Trusted Types (fix in the page with
  `<!--email_off-->…<!--/email_off-->`, no dashboard access needed), and a zone with Web Analytics on injects the beacon
  even when `site.analyticsToken` is empty: the privacy page must then disclose it. Toolkit and notes: `~/projects/sites/mockups/scripts/dev/live/`
  (README). Build-side defences every site should carry: `data-cfasync="false"` on each `<script src>`, `?v=<hash>` on CSS
  and JS, `X-Robots-Tag: noindex` for the project's pages.dev hosts (details: `cloudflare-pages-gotchas`).
- **Chuka tests every live site from outside, as part of shipping (Will, 2026-11-18).** After every production
  deploy (the next 15:00 CT; many deploys in a day = one test) and once a month (each site's `monthly_day`), he runs
  an external test from hermes: transport, DNS, every sitemap page, markup and JSON-LD, PageSpeed, headers and
  exposure, agent files, site specifics. Sites: williejackson.com, abernathymagazine.com, j2wtalent.com, listed in
  homelab-ansible `playbooks/files/chuka-site-tests/sites.json` (what each site is, private paths checked by status
  only, forms he must never submit, and `known`: what has already been judged). **A new site joins that file at
  launch** (redeploy homelab-report-timers.yml; its first test goes out at the next 15:00, or
  `systemctl start chuka-site-test.service` on ansible-ctrl for now). The 16:00 analysis grades his reply; findings
  reach my daily queue: verify each against the site before acting (his 11-18 run had one false positive), fix the
  minor ones, take DNS and anything outward-facing to Will, and add settled items to `known` so he doesn't re-report
  them. One site a day, one model turn: keep each site's brief under 9,000 bytes. Code: `scripts/chuka-site-test.py`,
  `chuka-duties.sh --sites`.
- **Validators from this network (2026-11-18).** validator.w3.org/nu throttles after ~40 pages and stays shut: send one
  page per template, and run `html-structure.py` over the rest. validator.schema.org answers with Google's bot wall:
  check JSON-LD against the vocabulary file with `schema-vocab.py`. The W3C feed validator and Wikipedia's Citoid API
  work. The W3C checker itself is installed on dev (`~/tools/vnu`, 2026-11-19): validate a whole crawled site in one local pass.
- **A hero that is a `<video>` paints its poster as the LCP image (2026-11-18).** A poster can't carry `fetchpriority`
  or `srcset`: use one WebP poster (a third of the JPEG's bytes; keep the JPEG for JSON-LD `thumbnailUrl`) and add
  `<link rel="preload" as="image" type="image/webp" fetchpriority="high">` for it on that page only.
- **Video embeds play in place, never redirect off-site, and match the content column's width (Will, 2026-11-07, Abernathy).** Use a same-page player (YouTube → youtube-nocookie embed, or Vimeo) instead of a thumbnail link to the platform; size the embed frame to equal the article's hero/image width (the container-size technique in the 'Images bigger than the text column' note above applies here too). This generalizes the click-to-play keynote facades already used on williejackson.com's About/Consulting pages — treat it as a standing rule for every site with embedded video, not a one-off for one article.

## 0. The non-negotiables (read even if you read nothing else)

1. **GRT first.** Golden Ratio Typography sets every font size, line height and spacing value. Run `grt.py` before writing CSS. Never hardcode type or spacing values.
2. **Color is proposed, never defaulted.** Give 2–3 OKLCH palette options per site, then wait for a pick.
3. **No AI-slop defaults.** See §7. When in doubt, the generic choice is the wrong one.
4. **Playwright screenshot loop before any UI is called done.** Desktop and mobile widths, then look at the screenshots and fix what you see.
5. **Performance ships by default.** Semantic HTML, `_headers`, sized/lazy images, self-hosted fonts, no render-blocking JS.
6. **Hand-written CSS. Vanilla JS. 11ty.** No Tailwind, no CSS or animation frameworks, no SPA frameworks, and don't propose switching to Astro.
7. **Confirm before deploying to production**, unless a project file says otherwise.
8. **Never commit or embed secrets.** That includes tokens in git remote URLs.
9. **Ship standard = specification.website (Will, 2026-11-05).** Every Required item and every Recommended item
   that applies, built in from day one via `starter/` (§15) and **proven with `starter/scripts/site-audit.py`
   against the deployed site** before any site is called done. Lighthouse targets: Accessibility, Best Practices,
   SEO and Agentic Browsing 100, Performance ≥ 95 (SEO is legitimately lower on a noindexed preview).

---

## 1. How to work with Will

- Planning and research happen in Claude.ai, and you do the implementation. Treat any spec file or checklist in the repo (`SPEC-*.md`, tiered checklists) as the brief.
- **Work in phases. Don't expand scope.** If something is marked "held" or "Tier 2," leave it alone and note anything you'd add for later.
- **Be opinionated, terse and prioritized.** Make a concrete recommendation with a one-line reason, not a menu of vague categories.
- **Before committing to any design direction, show 2–3 concrete options** (type pairing, palette, layout) and offer to mock them up. Commit fully once Will picks.
- Identify the mode up front: **New site**, **Migration** (WordPress → 11ty) or **Add page**. Ask if it's unclear.
- For a new site, collect: project slug, purpose/audience (1–2 sentences), aesthetic direction, base font size, content column width, brand colors or references, and whether search/pagination is needed.
- **No manual steps beyond the terminal.** If something can only be done in a dashboard (custom domains, Git connection), say exactly where to click.
- When revising, **preserve Will's own edits and wording.** List any text you changed.
- Will prefers methodical, repeatable systems over one-off fixes. If something will recur across sites, suggest making it a plugin, include or script.
- Avoid jargon in UI copy and in explanations.

---

## 2. Stack defaults

| Layer | Default |
|---|---|
| Generator | Eleventy (11ty) v3, Nunjucks + Markdown |
| CSS | Hand-written, custom properties, GRT tokens. No frameworks. |
| JS | None by default. Vanilla, `defer`red. Use islands (`<is-land>`) for anything heavy. |
| Typography | GRT (`grt.py`) → Utopia fluid type calibrated to GRT |
| Color | OKLCH tokens |
| Images | Build-time pipeline: AVIF + WebP fallback, originals untouched (see §10) |
| Search | Pagefind (post-build, static, no service) |
| SEO | `eleventy-plugin-jackson-seo` (Will's private GitHub plugin) when available |
| CMS (if editing needed) | Sveltia CMS (git-based, mobile-friendly) |
| Hosting | Cloudflare Pages, Git-integrated with GitHub |
| QA | Playwright screenshots |

### Scaffold

```
{slug}/
├── src/
│   ├── _includes/   base.njk, nav.njk, footer.njk (+ post.njk etc.)
│   ├── _data/       site.js  (name, url, description, author: "Willie Jackson")
│   ├── css/         grt.css (GENERATED, never hand-edit) + style.css
│   ├── images/      source originals (never modified)
│   ├── fonts/       self-hosted woff2
│   └── index.njk
├── public/          _headers, _redirects  (passthrough to _site root)
├── scripts/         image pipeline, etc.
├── eleventy.config.js (or existing .eleventy.js; match what's there)
├── package.json     scripts: dev, build, build:prod, deploy:preview, deploy:prod
└── wrangler.toml    minimal: name + pages_build_output_dir = "_site"
```

`.gitignore`: `node_modules/ _site/ .DS_Store .env .dev.vars`. `_site/` is always a build artifact.

---

## 3. Typography

### GRT is mandatory and comes first
The calculator lives at `~/.claude/tools/grt.py` (copy it there, or into the repo's `scripts/`).

```bash
python3 ~/.claude/tools/grt.py --font-size 18 --content-width 680 --x-height 0.49 \
  --target body --output src/css/grt.css
```

| Site type | font-size | content-width |
|---|---|---|
| Content / article / magazine | 18 | 680 |
| Portfolio / professional | 17 | 720 |
| Marketing / landing | 16 | 860 |
| Documentation | 16 | 680 |

- `--content-width` is the **readable column** (the article's `max-width`), not the page width.
- x-height: Georgia/Merriweather/Lora 0.49 · Playfair 0.47 · Source Serif 0.50 · DM Sans/Nunito Sans/Work Sans 0.53 · most other sans 0.52. Measure it if the font isn't listed.
- Always `--target body`. Regenerate (don't edit) when base size, column width (>40px change) or primary typeface changes.
- Tokens it produces: `--grt-scale-1..6`, `--grt-lh-1..6`, `--grt-h1-size..h6-size`, `--grt-h1-lh..h6-lh`, `--grt-space-xs|sm|md|lg|xl|xxl`, `--grt-content-width`.
- Map: body → `scale-1`/`lh-1`; paragraph margin → `space-md`; heading top margin → `space-lg`; section padding → `space-xl`; component gap → `space-sm`. Only one derived value is allowed: metadata/bylines at `calc(var(--grt-scale-1) * 0.85)`.
- Load `grt.css` via a `<link>` before `style.css`. **Do not also `@import` it** from `style.css`, because that loads it twice.

```css
/* Never */  h1 { font-size: 42px; line-height: 1.2; }
/* Always */ h1 { font-size: var(--grt-h1-size); line-height: var(--grt-h1-lh); }
```

### Then make it fluid (Utopia, anchored to GRT)
GRT values are the **max-viewport** sizes. Generate Utopia `clamp()` steps so the large end equals GRT:
- Max: base = GRT base; ratio = √φ ≈ **1.272** (this lands step 1–4 on GRT's h4, h3, h2, h1 exactly).
- Min (around 360px viewport): base 1–2px smaller, ratio ~1.2.
- Formula: `slope = (max − min) / (maxVw − minVw)`; `clamp(min, (min − slope·minVw) + slope·100vw, max)`. Express sizes in **rem**, not px, so a user's browser font setting is respected.
- Convert GRT line heights to unitless ratios (`lh / size`) so they scale with fluid sizes.

### Typefaces
- **No house style.** Every site gets its own pairing, proposed as 2–3 options tied to the aesthetic direction.
- Not as defaults: Inter, Roboto, Arial, system-ui-only. Also avoid reaching for the stock "AI editorial" pairings (Playfair + Source Serif, Instrument Serif + DM Sans, Fraunces + anything) unless Will picks one on purpose.
- Prefer one family with hierarchy through weight and size, or one deliberate pair. Use 4–5 sizes, reused.
- Self-host `woff2` in `src/fonts/`, subset where possible, `font-display: swap`, and preload only the primary body face.

---

## 4. Color
- OKLCH everywhere: `--color-bg`, `--color-text`, `--color-accent`, `--color-border`, `--color-muted`, all on `:root`.
- **Propose 2–3 palettes and wait.** Never ship a placeholder palette as the real one.
- Contrast: 4.5:1 for body/small text, 3:1 for large text and UI. A bright accent usually fails at small sizes, so use it for large text, shapes and markers and derive a darker, text-safe variant for links and labels.
- Client work: get the **real, current** brand first (live site computed styles, current template, logo files). Check dates, because old templates lie.

## 5. Layout and design
- **Choose layout from the content**, not from a template: a real timeline, a real table, split panels, plain lists separated by rules.
- Vertical rhythm comes from GRT spacing tokens only.
- Vary the pacing. Sparse sections, dense working sections and generous whitespace on statements. Not every section should have the same margins, density and structure.
- At most one brand-native motif, used sparingly and consistently.
- Reference shelf (study for craft, don't copy): craigmod.com, andy-bell.co.uk, frankchimero.com, robinrendle.com, klim.co.nz.
- Aesthetic lanes to offer when no direction is given: editorial/magazine, luxury/refined, brutalist/raw, warm/professional, minimal/clean, bold/expressive.

## 6. Motion
- Transitions only. Use native cross-document View Transitions (`@view-transition { navigation: auto; }`) as progressive enhancement.
- No animation libraries unless justified in writing first.
- Always honor `prefers-reduced-motion`.

## 7. Never do these (AI-slop tells)

**Visual**
- Cream/beige backgrounds with terracotta or brick-red accents (the default AI palette)
- Generic serif-plus-sans "editorial" pairings unrelated to the brand
- Small uppercase, letter-spaced eyebrow labels above every heading
- Colored accent bars on every block
- Rows of identical rounded, thin-bordered cards, section after section
- "01 / 02 / 03" numbering used as decoration
- Italic pull quotes with a colored left border (use large plain text with real quotation marks and thin rules instead; override GRT's default blockquote border if needed)
- Stat tiles giving many numbers equal weight, and invented round numbers
- "Diagrams" that are a row of boxes with arrows
- Decorative elements that carry no meaning; generic stock imagery
- **Image hover zoom/scale effects** (`transform: scale()` on `:hover`)
- The same footer text repeated for no reason

**Copy** (if you write any placeholder or real copy)
- Em dashes; "It's not X, it's Y"; reflexive groups of three; colon titles everywhere; filler that could belong to anyone; jargon
- Never invent testimonials, stats or client names. Use obvious `[PLACEHOLDER]` markers.

---

## 8. HTML and accessibility (every page)
- `<html lang="en">`; one `<h1>` per page (the page title, not the site name); no skipped heading levels
- `<main>`, `<nav>`, `<footer>` landmarks; `<article>` for posts and cards
- Descriptive `alt` on every `<img>` (`alt=""` only for decorative images)
- `<time datetime="YYYY-MM-DD">` for dates; `aria-label` on icon-only links and buttons
- Visible focus styles; full keyboard navigation; nav and footer get `data-pagefind-ignore`
- **Target: Lighthouse/PageSpeed Accessibility 100 and Agentic Browsing 100** (Will, 2026-11-02). Agentic
  Browsing (Lighthouse 13+) scores a well-formed accessibility tree plus CLS, so the rules above are
  most of it; also `title` on every `<iframe>` (including ones embed scripts create) and `width`/`height`
  on every `<img>`. Verify against **every** page, not a sample: on williejackson.com, 5 of 58 pages had
  content-level failures the template runs never showed. Running Lighthouse here: memory
  `reference_lighthouse_on_claude_code_host` (the PSI API needs a key)

## 9. SEO and sharing
- Every page: description (150–160 chars), canonical (absolute), and the full share set: `og:site_name`, `og:type`
  (`article` for posts), `og:title`, `og:description`, `og:url` (= canonical), `og:image` + `og:image:type`/`width`/
  `height`/`alt`, `twitter:card = summary_large_image`. All URLs **absolute**. `starter/src/_includes/head.njk` does it.
- **`og:image` is a 1200×630 JPG** (not WebP: support is inconsistent and Will cross-posts to LinkedIn), cropped on
  purpose with `starter/scripts/og-crop.cjs` and looked at. Site default plus a per-page `ogImage` (each post uses its
  own photo). Without OG tags, Messages/LinkedIn pick an image themselves (Abernathy's preview showed the wrong
  photo, 2026-11-05). Share images are exempt from `Cross-Origin-Resource-Policy: same-site`.
- JSON-LD `@graph` with `@id` cross-links: Person ("Willie Jackson") or Organization, WebSite, BlogPosting,
  WebPage/CollectionPage, BreadcrumbList (`starter/src/_includes/jsonld.njk`). Use `eleventy-plugin-jackson-seo`
  instead if it's installed and covers the same ground.
- Generated at build time: sitemap.xml, robots.txt (AI policy below), **llms.txt** (Recommended by the spec; it was
  "skip unless asked" before 2026-11-05), an Atom feed with `<link rel="alternate">` on sites that publish posts.
- **AI crawlers (Will, 2026-11-05):** allow AI search and answers (OAI-SearchBot, ChatGPT-User, Claude-SearchBot,
  Claude-User, PerplexityBot), block training (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, CCBot, …), plus
  `Content-Signal: search=yes, ai-input=yes, ai-train=no`.
- No `security.txt` (Will skipped it 2026-11-05: no contact address to publish).
- **Citation tags on posts (Abernathy, 2026-11-08).** Wikipedia's citation tool (Citoid) ignores JSON-LD for authors and
  scrapes the visible byline ("Alexander Hardy7 min"). Add Dublin Core (`<link rel="schema.DC" …>`, `DC.title`,
  `DC.creator` as "Last, First", `DC.date`, `DC.publisher`) plus `<meta name="author">` in **natural order with no degree
  or Jr./II suffix**: on a Cloudflare custom domain Citoid falls back to a scraper that reads only that tag and takes the
  last word as the surname. **Not Highwire `citation_*`**: it makes every post a journal article with no journal, which
  Wikipedia flags as an error. **`og:title` on an article is its bare title** (no "· Site" suffix; `og:site_name` names
  the site): on the live domain Citoid takes the title from `og:title` (williejackson.com cited posts as "Title · Willie
  Jackson" until 2026-11-18). Test against the real tool, preview *and* live (they took different paths):
  `curl https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/<urlencoded URL>`. Abernathy repo: filters
  `citationName`/`plainName` in `eleventy.config.js`.

## 10. Performance

### Images
- Source originals live in `src/images/` and are **never modified**. The build generates derivatives (prefer `@11ty/eleventy-img` or a `sharp` script): **AVIF primary, WebP fallback** via `<picture>`, responsive `srcset`/`sizes`, blur-up LQIP for large photos.
- Always set `width` and `height` (or `aspect-ratio`) to prevent layout shift.
- LCP/hero image: `fetchpriority="high"` and **no** `loading="lazy"`. Everything below the fold gets `loading="lazy" decoding="async"`.
- Never replace an image in place under the same filename (it's cached as immutable). Rename it instead.
- SVGs pass through untouched.

### Speed and perceived speed, built into `starter/` (Will, 2026-11-05)
- **Images:** `@11ty/eleventy-img`'s HTML transform turns every `<img>` into AVIF → WebP → JPEG at 320/640/960/1600 with
  width/height, lazy by default. The first-screen image (hero; first rows of a list) is `loading="eager"
  fetchpriority="high"`. Plain-colour placeholder tint while photos load, not Base64 blur-ups: those need `data:` in
  the CSP and grow every page.
- **Fonts:** `scripts/fonts.mjs` subsets to Latin WOFF2 (variable axes kept) and writes size-matched local fallbacks
  (`size-adjust` + ascent/descent overrides), so text doesn't jump on swap; preload only the first-screen body font;
  `check-glyphs.mjs` catches characters the subset lacks.
- **Navigation:** speculation rules **prerender** on hover/press, plus cross-document **View Transitions** (reduced-motion
  aware, §6).
- **Long lists:** `.cv-auto` (`content-visibility: auto`) on repeated rows.
- **Measure real visitors** with Cloudflare Web Analytics at launch (`site.analyticsToken`); check Early Hints on the
  production domain.
- **Base64:** don't, except things under ~1 KB. **Don't use** Rocket Loader (rewrites scripts, breaks the CSP), Auto
  Minify (retired), Polish/Mirage (build-time beats them), Argo/Tiered Cache (pointless for static), Zaraz (only if a
  site must carry third-party tags). Inline all CSS only on one-page sites, with its CSP hash generated at build.

### CSS, JS and fonts
- All CSS in `src/css/`. Inline only critical above-the-fold CSS.
- Fingerprint CSS URLs (a content-hash query string via an 11ty filter) so the immutable cache rule is safe.
- Every `<script>` gets `defer` or `async`. Zero JS is the target for content pages.

### `_headers` (generated: `starter/src/_headers.njk`)
Cloudflare **joins duplicate headers with commas** when several rules match, so never put `Cache-Control` on `/*`,
and detach an inherited header with `! Name` before overriding it on a sub-path. Security headers go on `/*` and
cache headers on asset paths only. The set (Will's decisions 2026-11-05):
- `Strict-Transport-Security: max-age=63072000` (**no `includeSubDomains`/`preload` by default**: they're hard to undo
  across a whole domain, so they're a per-domain decision for Will)
- `Content-Security-Policy: default-src 'self'; script-src 'self' 'inline-speculation-rules'; style-src 'self'; img-src 'self';
  font-src 'self'; connect-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self';
  frame-ancestors 'none'; upgrade-insecure-requests; require-trusted-types-for 'script'` (so: no inline scripts or
  `style=""`; each third party is added deliberately and tested on a branch deploy first)
- `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()`,
  `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-site` (share images: `cross-origin`),
  `X-Permitted-Cross-Domain-Policies: none` (added 2026-11-18 after an ssl.org scan of williejackson.com)
- **Caching stays off until launch** (Will, 2026-11-05, refining the 10-23 hold): `site.launched` turns on immutable
  caching for `/css/*` (fingerprinted by the `fp` filter), `/fonts/*`, `/img/*`. Never `X-XSS-Protection` (spec: avoid).
(A `/*.html` rule does not match 11ty's pretty URLs like `/about/`, so don't use one.)

### Pre-deploy Core Web Vitals check
- [ ] LCP image is prioritized and not lazy
- [ ] All images have dimensions and AVIF/WebP derivatives exist in `_site/`
- [ ] Fonts don't shift layout
- [ ] `_site/_headers` (and `_redirects` if any) exist after build
- [ ] No render-blocking scripts
- [ ] Heading hierarchy is clean
- [ ] Playwright screenshots reviewed at ~390px and ~1280px
- [ ] `site-audit.py` on the deployed preview: 0 FAIL (§15)

---

## 11. WordPress → 11ty migrations
- Prefer a clean migration (no headless WordPress). Use `@11ty/import` (or `wordpress-export-to-markdown` if a project already uses it) to produce `src/posts/*.md` with frontmatter and downloaded images.
- **Preserve URLs exactly.** Use computed permalinks that match the old structure, plus `public/_redirects` 301s for anything that moves. Test 3–5 old URLs.
- **Preserve RSS GUIDs** in WordPress `?p=<id>` form so subscribers don't get re-flooded. Use `@11ty/eleventy-plugin-rss`.
- Build-time pagination (12 per page), category pages, Pagefind with `data-pagefind-body` on articles and `data-pagefind-filter="category:…"`. Pagefind runs **after** eleventy in the `build` script.
- Before the first deploy, confirm the post count in `_site/` matches WordPress and that category pages, `/page/2/`, the search index, image derivatives and redirects all work.

## 12. Deploy (Cloudflare Pages + GitHub)
- **Create long-lived sites in the Cloudflare dashboard with Git integration** (Pages → Create → Connect to Git; build `npm run build`, output `_site`). Pushing to `main` deploys production; any other branch gets a preview URL.
- **Do not run `npx wrangler pages project create` for a real site.** That makes a Direct Upload project, which can never be switched to Git integration. Direct Upload is fine only for throwaway mockups. Git-integrated projects can still take manual `wrangler pages deploy` uploads when needed.
- Keep `wrangler.toml` minimal. Its `name` must equal the Pages project name.
- Custom domains are set up in the dashboard (Pages → project → Custom domains).
- Secrets: `.env`/`.dev.vars` are gitignored; use `wrangler pages secret put`. Authenticate git with `gh auth login` or a credential helper. **Never embed a PAT in the remote URL.**
- Git: stage specific files (no blind `git add -A`), use conventional commits (`feat: fix: style: chore: docs: refactor:`), and never force-push `main`.
- Pushing to `main` is a production deploy, so **confirm first** unless the project's `CLAUDE.md` says to auto-push.

### End every session that changed files with:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEPLOY: {Project}
Preview:     git push origin <branch>   (or npm run deploy:preview)
Production:  git push origin main       (or npm run deploy:prod)
Changed:     <files>
Check:       <URLs to eyeball>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 13. Known projects (move these into each repo's own CLAUDE.md)
- **williejackson.com.** *Status 2026-11-01:* an **interim** static copy on Pages (Git-integrated project `williejackson-com-static`, repo `jackson2w/williejackson-com-static`, `public/`), exported from a private WordPress on homelab CT 144 (`wordpress.tail922cee.ts.net/wp-admin`, Tailscale only). See `wordpress-static-export`. **D-33 DECIDED 2026-11-13 (Will): 11ty, no WordPress.** The Darkroom mockup (rules variant; Libre Caslon Display + IBM Plex Sans/Mono, GRT 18/680, `~/projects/sites/mockups`) is the basis for the 11ty rebuild, not a WordPress theme. CT 144 (the WordPress publisher) and the Thesis/Focus theme stay live only until the 11ty site ships; build-start date asked 11-17. The static export to Pages stays interim until then. Flat root-level permalinks with no dates; preserve them exactly. Memory `project_williejackson_static_site` has the theme requirements. **schema.org JSON-LD is required on the redesign (Will, 2026-11-07)**, emitted by the theme: Person `https://williejackson.com/#person` (sameAs LinkedIn + his Abernathy author page) at the centre, About = ProfilePage, posts = BlogPosting authored by that @id, breadcrumbs from the visible trail, every exported page checked (port mockups `scripts/abernathy-check-jsonld.py`). Full spec in that memory. Needs positioning content tying Will to talent management.
  *Events (Will, 2026-11-12):* the record of every event Will produced, hosted or spoke at lives on williejackson.com under **/events/** (index + one page per event), credited to the banner it ran under ("Presented by *Abernathy*", "Hosted by BREAD"); the banner is a credit, never the structure. Each page is a **new third-person write-up** with its own canonical plus an "Original recap in Abernathy →" link; never `rel=canonical` to the Abernathy copy (it sends ranking to a site nobody visits). schema.org `Event` JSON-LD with organizer = Will's Person. Curated photos on the page, photographer credited; nav is Posts · About · Events · Contact. Full decisions: memory `project_williejackson_darkroom_mockup`.
- **abernathymagazine.com.** *Decided 2026-11-04:* one-time WordPress (WP Engine) → 11ty import, no WordPress kept (426 posts 2015–2018, 195 authors; a dormant archive, so the homepage is a gateway). Repo `jackson2w/abernathymagazine` (its April 2026 single-page mockup is superseded); auto-commit and push after every change (project override of §12). Type: **Libre Caslon Display** headlines + **IBM Plex Sans** text (+ Libre Caslon Text italic for deks, Plex Mono for counts); GRT from Plex at 18px / 640px text / 1080px image column. Palette: **Liberation on cream** (cream paper, espresso ink, red/black/green; deeper red/green for fields under cream text). Direction: **Broadside** (the Black press: Emory Douglas's Black Panther paper; hard paste-up shadows cycling red/ink/green, swallowtail section flags, rubber-stamp cover caption, off-register red wordmark, black-plus-one-colour duotone lead, cropped outline footer wordmark). Homepage order: cover (`2015/03/Abernathy-Men.jpg`) → Featured (Will's 7 + launch recap) → publisher's list (Editor's Picks) → Sections as **Shelves** (11 approved sections, 4 thumbnails each, one per writer) → Series (9) → Tags → archive by year + search + "Read something at random". **No contributors section on the homepage** (Will). Keep the old theme's drop cap + lead-in phrase. Will still wants custom text treatment, letter spacing and layout tweaks. Mockup and data scripts: `~/projects/sites/mockups` (`/abernathy/broadside/`, `scripts/abernathy-*.py`, `scripts/dev/`). No image hover zoom.
- **photos.jackson2w.com.** Photo pipeline: AVIF, Display-P3, blur-up LQIP, EXIF extraction via prepare scripts.

## 14. Decisions log (where older skill notes were superseded)
- `llms.txt` "low priority, skip unless asked" → **built by default** (specification.website Recommended, 2026-11-05).
- `X-Frame-Options: SAMEORIGIN` alone → **CSP `frame-ancestors 'none'` + `X-Frame-Options: DENY`**, plus HSTS, CSP,
  Permissions-Policy, COOP/CORP (2026-11-05).
- A hand-maintained `public/_headers` → **generated from `site.launched`**, one launch switch (2026-11-05).
- WebP-only at quality 85 → **AVIF + WebP fallback** (matches the newer photo pipeline).
- Hex color tokens → **OKLCH, proposed per site**.
- Static px GRT → **GRT + Utopia fluid, in rem**.
- The suggested font-pairing list and the terracotta `#c45c2e` example accent were **dropped** because they match the slop defaults in §7.
- The "pull quotes: italic + left border" magazine pattern was **dropped** (§7).
- `wrangler pages project create` as step one → **dashboard Git integration** (Direct Upload lock-in).
- The `_headers` `/*.html` rule plus HTML Cache-Control → **security headers on `/*`, cache rules on assets only**.
- `grt.css` both linked and `@import`ed → **linked only**.
- `wordpress-export-to-markdown` → **`@11ty/import` preferred**.

## 15. Ship standard: specification.website (adopted 2026-11-05)

Will: "I want these preferences around semantic markup and web performance and Google Lighthouse scores and open
graph tags to be built into all the websites that you build for me." The bar is **specification.website**
(Joost de Valk; 178 topics, each Required / Recommended / Optional / Avoid; CC BY 4.0). Use the
`specification-website` skill to look items up (it also has the MCP endpoint and the per-page `.md` URLs).

- **Build it in, don't bolt it on:** start every site from `starter/` (README there). It already covers the
  foundations, SEO, sharing, structured data, security headers, agent readiness (llms.txt, robots AI policy,
  Content-Signal), resilience (real 404, manifest) and performance (speculation rules, fingerprinted CSS, caching at
  launch) items that apply to a static 11ty site on Cloudflare Pages. §2–§10 still govern the design and the rest.
- **Prove it:** `python3 starter/scripts/site-audit.py <deployed url> [--preview]` checks the deployed site (headers
  and status codes only exist there) and exits 1 on any FAIL. It was checked both ways on 2026-11-05:
  specification.website itself scored 0 FAIL, and the live WordPress abernathymagazine.com scored 7 real FAILs.
  Then Lighthouse on every template (§8).
- **Out of scope for static sites unless the site needs them:** cookie consent (no cookies), forms and
  authentication items (unless the site has forms), i18n/hreflang (English-only sites), WebAuthn/OAuth well-knowns,
  MCP/A2A/commerce agent protocols. Markdown source endpoints (`/page.md`) are worth adding on content-heavy sites (a
  magazine): decide per site.
- **Privacy page: decided 2026-11-05.** `starter/src/privacy.njk`, linked from every footer. Publisher "Willie Jackson",
  contact `security@jackson2w.com`, no postal address; Will approved the facts (no cookies, ads or tracking; Cloudflare
  hosting; cookieless Web Analytics, whose paragraph appears only when a token is set). Retention figures come from
  Cloudflare's docs (7 days full detail, then about 10%; six months viewable). A site that adds anything that collects
  data must update the page in the same change. `site-audit.py` fails a launched site whose homepage doesn't link it.
- **Still Will's call per domain:** `includeSubDomains`/`preload` for HSTS; a security.txt (skipped 2026-11-05).
- **Staying current:** the spec changes often (agent readiness especially). Monthly, read
  `https://specification.website/changelog/rss.xml` since the last check (date in the follow-up) and update
  `starter/`, this section and `site-audit.py` for any new or promoted item. Last checked: 2026-11-05.


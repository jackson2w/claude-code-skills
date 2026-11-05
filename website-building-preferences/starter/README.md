# Starter kit: Will's ship standard, built in

Every new 11ty site for Will starts from these files. They put specification.website's Required and
Recommended items (adopted 2026-11-05) into the build itself, so nobody has to remember them page by page.
Proven end to end on 2026-11-05: a throwaway site built from this kit and deployed to a Pages branch
passed `site-audit.py` with 90 checks, 0 real failures.

## Use it

1. Copy `src/`, `scripts/`, `eleventy.config.js` and `.gitignore` into the new repo (merge into existing files).
   ```
   npm i -D -E @11ty/eleventy@3.1.7 @11ty/eleventy-plugin-rss@2.0.4 @11ty/eleventy-img@7.1.1 subset-font@2.9.0 @capsizecss/unpack@4.0.1 @capsizecss/metrics@4.4.0
   ```
   package.json: `"type": "module"` and
   `"build": "node scripts/fonts.mjs && eleventy && node scripts/check-glyphs.mjs"`. Cloudflare Pages runs `npm run build`.
2. Fill every `[REPLACE]`/`[bracket]` in `src/_data/site.js`. Leave `launched: false`.
3. Share image: `NODE_PATH=/usr/lib/node_modules node scripts/og-crop.cjs <photo.jpg> src/img/og/default.jpg [focalY]`
   (dev box; 1200×630 JPG). Look at the crop.
4. Icons from one letter of the site's own typeface (needs the font as TTF/OTF, and `opentype.js` in a scratch dir:
   `npm i opentype.js@1.3.4` in `/tmp/fav`):
   `NODE_PATH=/usr/lib/node_modules:/tmp/fav/node_modules node scripts/make-icons.cjs <font.ttf> <letter> public "<bg>" "<fg>" ["<shadow>"]`
   Writes `public/favicon.svg|ico`, `public/apple-touch-icon.png`, `public/icons/icon-192|512|maskable-512.png`.
   Check the 32 px version still reads (`tail -c +23 favicon.ico > x.png`).
5. Fonts: put the original TTF/OTF/WOFF2 files in `src/fonts-src/` (never edited) and list them in `site.fonts`. In CSS
   always name the fallback second: `font-family: "IBM Plex Sans", "IBM Plex Sans Fallback", sans-serif;`.
6. Photos: originals go in `src/img/` and pages use plain `<img src="/img/…" alt="…">`; the build makes the
   AVIF/WebP/JPEG `<picture>`. Give each image a real `sizes` for its column (`sizes="8rem"` for a thumbnail). **The
   largest thing on the first screen loads eagerly:** `loading="eager" fetchpriority="high"` on the hero, and in list
   templates on the first row or two (`{% if loop.index <= 2 %}loading="eager"{% endif %}`). Everything else stays lazy.
7. Long lists: `class="cv-auto"` on each repeated row/card, with `--cv-size` set to its usual height.
8. Layouts include `head.njk` inside `<head>` (see `base.njk`) and link CSS through `| fp`.
   Posts: a directory data file with `{ "tags": "posts", "ogType": "article", "ldKind": "post" }` and a `date`.
   Pages that list things: `ldKind: collection`. Nested pages: `breadcrumbs: [{ name, url }]`.
9. Build, deploy a preview, then run the audit (below). Fix every FAIL before calling it done.

## What each file does

| File | Spec items it covers |
|---|---|
| `_includes/head.njk` | charset, viewport, title, description, canonical, meta robots (pre-launch), theme-color, color-scheme, favicons + manifest, feed discovery, Open Graph + X card (absolute URLs, 1200×630, alt), speculation rules |
| `_includes/jsonld.njk` | structured data: WebSite + Person/Organization, BlogPosting, WebPage/CollectionPage, BreadcrumbList, cross-linked by `@id` |
| `_includes/base.njk` | `lang`, skip link, `header`/`main`/`footer` landmarks, fingerprinted CSS |
| `_headers.njk` | HSTS (2 years, no preload), strict CSP with Trusted Types, frame-ancestors + X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, COOP/CORP (share images exempt), noindex before launch, caching after launch |
| `robots.txt.njk` | pre-launch: disallow all. Launched: AI training bots blocked, AI search bots allowed, `Content-Signal: search=yes, ai-input=yes, ai-train=no`, Sitemap line |
| `sitemap.xml.njk`, `llms.txt.njk`, `site.webmanifest.njk`, `404.njk` | XML sitemap, llms.txt, PWA manifest, a real 404 with the site's own layout |
| `eleventy.config.js` | passthroughs, `fp` filter, RSS plugin filters, Atom feed (`site.feed`), image transform (AVIF → WebP → JPEG at 320/640/960/1600, width/height, lazy by default) |
| `scripts/fonts.mjs` | before the build: subsets each font to Latin as WOFF2 (keeps variable axes), writes `css/fonts.css` with hashed URLs and a size-matched local fallback per family (no text jump when the font arrives), and the preload list |
| `scripts/check-glyphs.mjs` | after the build: warns if any page uses a character the subset fonts lack |
| `src/css/starter.css` | cross-document View Transitions (reduced-motion aware), `scrollbar-gutter`, image placeholder tint, `.cv-auto` |
| `scripts/site-audit.py` | checks a deployed URL against all of the above |

## Measured on the throwaway test site (2026-11-05)

- Fonts: IBM Plex Sans variable 537 KB → 71 KB, Libre Caslon Display 101 KB → 27 KB, both axes kept.
- Photos: 41 originals, AVIF chosen by the browser; first build 35–49 s on the dev box, then ~1 s from `.cache/`.
- Lighthouse mobile: Performance 100 on home and a 40-image list; LCP 1.4 s; CLS ≤ 0.009; home 153 KB, list 231 KB.
- Prerender on hover: Chrome starts it (CDP shows it); automation always reports `PrerenderingDisabledByDevTools`, so
  it can't be proven in a headless test, and the prefetch fallback serves the click there.

**Big image libraries:** AVIF encoding costs about a second per image per build without a cache. A site with
hundreds of photos (Abernathy) must keep `.cache/` between Cloudflare builds, or have the derivatives built once and
committed, or the 20-minute Pages build limit comes into play. Decide that at import time.

## The CSP is strict on purpose

`script-src 'self'` plus one inline exception for speculation rules; `style-src 'self'`; no third parties.
So: **no inline `<script>` or `style=""` attributes** (move them to files or classes), and every third-party
service (analytics, embeds, fonts CDN) has to be added to the policy deliberately. Test a new policy on a branch
deploy with a browser console check before production (Abernathy 2026-11-05 did this: 0 violations).

## Launch day (one switch, plus the things only Will can supply)

- `launched: true` in `site.js`. That removes noindex (meta and header), opens robots.txt with the AI policy and
  Sitemap line, and turns on asset caching (CSS is fingerprinted; never replace an image or font in place: rename it).
- **Privacy page** (Required): `src/privacy.njk`, linked from `footer.njk`. Will approved its facts 2026-11-05
  (publisher Willie Jackson, contact security@jackson2w.com, no postal address; no cookies, ads or tracking; Cloudflare
  hosting and cookieless Web Analytics). The analytics paragraph appears only when `site.analyticsToken` is set. If a
  site adds anything that collects data (a form, an embed, a newsletter), update the page and `site.privacy.updated`.
- DNS: a CAA record allowing only the CA Cloudflare uses; IPv6 is automatic on Cloudflare.
- **Cloudflare Web Analytics** (free, cookieless; real visitors' Core Web Vitals, which Lighthouse can't see): in the
  dashboard, Analytics & Logs → Web Analytics → Add a site → manual snippet; put the token in `site.analyticsToken`.
  The head and the CSP pick it up only once `launched` is true. Don't also enable the Pages auto-inject toggle (it
  would add a second, CSP-blocked copy). Check that prerendered pages aren't double-counted.
- **Early Hints:** on the production domain, check that Cloudflare sends `103 Early Hints` for the font preload
  (`curl -sv https://<domain>/ -o /dev/null 2>&1 | grep -i "103\|link:"`). It did not happen on a pages.dev address
  (2026-11-05). If it's absent, turn on Early Hints in the zone's Speed settings.
- Uptime monitoring for the production URL.
- Run `site-audit.py <production url>` (no `--preview`) and Lighthouse on every page template (preferences §8).

## Audit

```
python3 scripts/site-audit.py https://<preview>.pages.dev --preview        # before launch
python3 scripts/site-audit.py https://<domain>                             # after launch
python3 scripts/site-audit.py https://<domain> --path /some/page/ --path /other/
```

Exit code 1 means a FAIL. Branch preview addresses (`<branch>.<project>.pages.dev`) always get Cloudflare's own
`X-Robots-Tag: noindex`; run the launched audit against production.

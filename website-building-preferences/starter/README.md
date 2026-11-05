# Starter kit: Will's ship standard, built in

Every new 11ty site for Will starts from these files. They put specification.website's Required and
Recommended items (adopted 2026-11-05) into the build itself, so nobody has to remember them page by page.
Proven end to end on 2026-11-05: a throwaway site built from this kit and deployed to a Pages branch
passed `site-audit.py` with 90 checks, 0 real failures.

## Use it

1. Copy `src/`, `scripts/` and `eleventy.config.js` into the new repo (merge the config into an existing one).
   `npm i -D @11ty/eleventy@3 @11ty/eleventy-plugin-rss@2`.
2. Fill every `[REPLACE]`/`[bracket]` in `src/_data/site.js`. Leave `launched: false`.
3. Share image: `NODE_PATH=/usr/lib/node_modules node scripts/og-crop.cjs <photo.jpg> src/img/og/default.jpg [focalY]`
   (dev box; 1200×630 JPG). Look at the crop.
4. Icons from one letter of the site's own typeface (needs the font as TTF/OTF, and `opentype.js` in a scratch dir:
   `npm i opentype.js@1.3.4` in `/tmp/fav`):
   `NODE_PATH=/usr/lib/node_modules:/tmp/fav/node_modules node scripts/make-icons.cjs <font.ttf> <letter> public "<bg>" "<fg>" ["<shadow>"]`
   Writes `public/favicon.svg|ico`, `public/apple-touch-icon.png`, `public/icons/icon-192|512|maskable-512.png`.
   Check the 32 px version still reads (`tail -c +23 favicon.ico > x.png`).
5. Layouts include `head.njk` inside `<head>` (see `base.njk`) and link CSS through `| fp`.
   Posts: a directory data file with `{ "tags": "posts", "ogType": "article", "ldKind": "post" }` and a `date`.
   Pages that list things: `ldKind: collection`. Nested pages: `breadcrumbs: [{ name, url }]`.
6. Build, deploy a preview, then run the audit (below). Fix every FAIL before calling it done.

## What each file does

| File | Spec items it covers |
|---|---|
| `_includes/head.njk` | charset, viewport, title, description, canonical, meta robots (pre-launch), theme-color, color-scheme, favicons + manifest, feed discovery, Open Graph + X card (absolute URLs, 1200×630, alt), speculation rules |
| `_includes/jsonld.njk` | structured data: WebSite + Person/Organization, BlogPosting, WebPage/CollectionPage, BreadcrumbList, cross-linked by `@id` |
| `_includes/base.njk` | `lang`, skip link, `header`/`main`/`footer` landmarks, fingerprinted CSS |
| `_headers.njk` | HSTS (2 years, no preload), strict CSP with Trusted Types, frame-ancestors + X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, COOP/CORP (share images exempt), noindex before launch, caching after launch |
| `robots.txt.njk` | pre-launch: disallow all. Launched: AI training bots blocked, AI search bots allowed, `Content-Signal: search=yes, ai-input=yes, ai-train=no`, Sitemap line |
| `sitemap.xml.njk`, `llms.txt.njk`, `site.webmanifest.njk`, `404.njk` | XML sitemap, llms.txt, PWA manifest, a real 404 with the site's own layout |
| `eleventy.config.js` | passthroughs, `fp` filter, RSS plugin filters, Atom feed (`site.feed`) |
| `scripts/site-audit.py` | checks a deployed URL against all of the above |

## The CSP is strict on purpose

`script-src 'self'` plus one inline exception for speculation rules; `style-src 'self'`; no third parties.
So: **no inline `<script>` or `style=""` attributes** (move them to files or classes), and every third-party
service (analytics, embeds, fonts CDN) has to be added to the policy deliberately. Test a new policy on a branch
deploy with a browser console check before production (Abernathy 2026-11-05 did this: 0 violations).

## Launch day (one switch, plus the things only Will can supply)

- `launched: true` in `site.js`. That removes noindex (meta and header), opens robots.txt with the AI policy and
  Sitemap line, and turns on asset caching (CSS is fingerprinted; never replace an image or font in place: rename it).
- A **privacy page** (Required): who runs the site, a contact, what data is collected (none, if there is no analytics),
  retention, rights, a "last updated" date. Will writes or approves the wording.
- DNS: a CAA record allowing only the CA Cloudflare uses; IPv6 is automatic on Cloudflare.
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

---
name: cloudflare-pages-gotchas
description: This skill should be used when working on a Cloudflare Pages project with Pages Functions — debugging on-the-fly image resizing that won't work, a wrangler.toml with named [env.*] blocks where bindings mysteriously go missing in one environment, a crypto.subtle PBKDF2 call that throws in production but works locally, or a _redirects rule that silently never fires on a path a Function also handles. Trigger phrases include "pages images binding", "env.IMAGES", "wrangler.toml env production", "bindings missing in production", "PBKDF2 iterations error", "NotSupportedError iteration counts", "_redirects not working", "redirect skipped by functions", "pages function precedence".
version: 0.1.0
---

# Cloudflare Pages + Wrangler Gotchas

Four real, non-obvious platform behaviors hit while building and deploying a
Cloudflare Pages site with Functions, KV, and R2. Each looked like a bug in
the project's own code at first; each was actually a documented (but easy to
miss) platform constraint.

## Pages Functions have NO Images binding — at all, ever

`env.IMAGES` (the on-the-fly image transform API) is unsupported on
Cloudflare Pages, full stop:

- `wrangler.toml`: an `[images]` block fails config validation on a Pages
  project.
- Dashboard: Images isn't in the Pages bindings list at all (it exists for
  Workers, not Pages).

This is a hard platform limit, not a config mistake to debug around.
**Solution: pre-generate the responsive/derivative images you need (WebP,
AVIF, thumbnails, etc.) at build or ingest time and serve them as plain R2
objects** — don't design around an on-the-fly resize step for Pages.
(Workers *do* support the Images binding; only Pages doesn't. `keep_vars` is
similarly Workers-only and will fail on a Pages project.)

## Empty `[env.production]` / `[env.preview]` blocks silently drop top-level bindings

In `wrangler.toml`, declaring *any* named environment block — even an empty
one — stops Wrangler from inheriting top-level `kv_namespaces` / `r2_buckets`
/ other bindings into that environment. The result: `pages deploy` (or a
branch deploy) ships with **no bindings at all**, and every Function that
touches one 500s in production while working fine locally.

```toml
# BAD — this empty block silently drops top-level bindings from prod:
[env.production]

# GOOD — no named env blocks at all; top-level bindings apply to every deploy
[[kv_namespaces]]
binding = "MY_KV"
id = "..."
```

Wrangler does print a warning about this during deploy, but still deploys
successfully — easy to miss in CI logs. Fix is simply deleting the empty
`[env.*]` blocks so the top-level config applies to all deploys (production
and preview alike).

## Workers' `crypto.subtle` caps PBKDF2 at 100,000 iterations

`crypto.subtle.deriveBits`/`deriveKey` with PBKDF2 throws
`NotSupportedError: iteration counts above 100000 are not supported` on
real Workers/Pages Functions — but **not** in `wrangler dev` or Miniflare,
which use Node's crypto implementation with no such cap. Code hashing at a
higher iteration count (210,000, matching some published bcrypt/PBKDF2
guidance) will pass every local test and then 500 on every request in
production.

**Lesson: PBKDF2/crypto.subtle behavior must be verified against a real
deploy, not just local dev** — Node-vs-workerd crypto differences hide this
kind of bug completely locally. If you store the iteration count alongside
each hash (e.g. `iterations` field in the stored credential), fixing a
too-high count is just re-hashing existing values, not a schema migration.

## `_redirects` is silently skipped for any path a Pages Functions route matches

Cloudflare's own docs: *"Redirects defined in the `_redirects` file are not
applied to requests served by Pages Functions, even if the Function route
matches the URL pattern."* This applies even when the matching function's
only job for that path is to call `next()` and pass through — the mere
existence of a matching Functions route is enough to disable `_redirects`
for that path.

**Practical impact: a root `functions/_middleware.ts` (which matches every
request) means `_redirects` never fires anywhere on that project, for any
path.** If you need a redirect (e.g. a renamed page/slug) on a Pages project
that has a catch-all middleware, implement the redirect *inside* the
middleware itself — checking `url.pathname` and returning
`Response.redirect(...)` — rather than relying on `_redirects` at all.

## `wrangler pages project create` now makes a *Workers* project (wrangler 4.149, 2026-10)

Seen 2026-10-23: `wrangler pages project create <name>` printed "Delegating to the latest version of
Cloudflare Pages, now part of Cloudflare Workers", **wrote a `wrangler.jsonc` (Worker + assets) into the
repo, rewrote `package.json` (added `deploy`/`preview` scripts and wrangler as a dependency), appended to
`.gitignore` and grew `package-lock.json` by ~1,500 lines**, then failed with "Pages project does not
exist". No Pages project was created. Every edit was local and uncommitted (`git checkout --` + delete the
jsonc to undo).

**To make a real Pages project, use the API, then deploy with wrangler as before**:
`POST /accounts/{id}/pages/projects {"name": "...", "production_branch": "main"}` (Pages Write token), then
`wrangler pages deploy _site --project-name <name> --branch main`. Deploying to an existing Pages project
is unaffected. Long-lived sites still go through dashboard Git integration (website-building-preferences §12).

## A custom domain on a proxied zone: what the headers really mean (2026-11-01, williejackson.com)

- **`cf-cache-status: DYNAMIC` on Pages HTML is normal.** That label describes the zone's CDN cache,
  which by default stores only static extensions (`.css`, `.jpg`…), never HTML. Pages serves the HTML
  from its own edge storage anyway: TTFB measured 0.12–0.16 s, no origin. Don't "fix" it with a Cache
  Everything rule: deploys don't purge the zone cache, so edits would stay invisible until the TTL ran
  out.
- **`cache-control: public, max-age=0, must-revalidate`** is Pages' default for HTML, so a new deploy
  shows at once (browsers revalidate by ETag).
- **Zone settings override `_headers` on the custom domain.** The same file served
  `max-age=86400` (from `_headers`) on `*.pages.dev` but `max-age=2678400` (31 days, the zone's
  Browser Cache TTL) on the custom domain. Compare the two hostnames before blaming `_headers`.
- **`! Header-Name` in `_headers` detaches a default header.** `! Access-Control-Allow-Origin` under
  `/*` drops Pages' default open CORS.
- **Cloudflare Fonts** (zone setting) rewrites a page's Google Fonts `<link>` at the edge into inline
  `@font-face` from `/cf-fonts/…`, so the browser never contacts Google. The `<link>` in the source
  is load-bearing; a `dns-prefetch` for `fonts.googleapis.com` is dead weight.
- **Moving a domain from an origin to Pages.** Add the custom domain in the dashboard; it offers to
  replace the existing proxied A record. A `www` → root redirect the old server did needs a zone
  Redirect Rule (template "Redirect from WWW to root") plus `www` as a second custom domain.
- **Early Hints on Pages needs explicit `Link` headers (Abernathy, 2026-11-07).** Pages generated no `Link` header
  from the HTML's `<link rel=preload>` tags on either `*.pages.dev` or the custom domain, so the zone's Early Hints
  switch had nothing to send. Put `Link: </css/x.css?v=hash>; rel=preload; as=style, </fonts/y.woff2>; rel=preload;
  as=font; type="font/woff2"; crossorigin` in `_headers` (generate it so fingerprinted URLs match), turn on Speed →
  Early Hints. Cloudflare sends `HTTP/2 103` from the second request on (the first primes it); check with `curl -sv --http2`.
- **Speed settings that fight a strict CSP:** Rocket Loader rewrites every script and injects its own (breaks Trusted
  Types); keep it off. Cloudflare Fonts only rewrites Google Fonts links (no-op for self-hosted fonts). Web Analytics
  in "JS snippet" mode injects nothing: count `beacon.min.js` per page to rule out double counting.
- **Rocket Loader was on for williejackson.com and nobody had checked (2026-11-18): no site JavaScript ran on the
  live domain for ~50 minutes after launch.** It retypes every `<script>` (`type="<hex>-text/javascript"`) and runs
  them by setting a script's text, which `require-trusted-types-for 'script'` blocks. Pages without Trusted Types kept
  working, which hid it. Zone features never run on `*.pages.dev`, so every preview check and served check passed.
  Defences, both in the site's own code so a dashboard toggle can't break it: `data-cfasync="false"` on every
  `<script src>` (Rocket Loader then skips them and injects nothing), and a deploy step that fetches the custom domain
  and fails on `rocket-loader`, `cdn-cgi/l/email-protection` or a retyped script (mockups `scripts/wj-preview-deploy.sh`).
  **After any cutover to a custom domain: crawl the custom domain and `cmp` each page with the build, and load pages
  in a browser reading the console.** On williejackson.com that diff showed exactly three zone features: Rocket
  Loader, Email Obfuscation, Automatic HTTPS Rewrites (it rewrote the Dublin Core namespace `http://purl.org/...`).
- **Fingerprint CSS and JS when the zone has a Browser Cache TTL (2026-11-18).** The zone told browsers to keep
  `/css/w4.css` for 31 days while HTML stays fresh, so returning visitors would pair new HTML with a month-old
  stylesheet. Add `?v=<content hash>` at build (Cloudflare's cache key includes the query string), fail the build on an
  unversioned reference, then `Cache-Control: public, max-age=31536000, immutable` on `/css/*` and `/js/*` is safe.
  Unversioned images keep the zone's month: rename a photo you replace.
- **The project's `*.pages.dev` hosts serve the same indexable site.** Keep them out of search from `_headers`:
  `https://<project>.pages.dev/*` and `https://:deploy.<project>.pages.dev/*`, each with `X-Robots-Tag: noindex`
  (host rules work; the custom domain is unaffected, verified).
- **Watch the custom domain against the project's own pages.dev host (2026-11-19, homelab-ansible
  `scripts/wj-site-watch.py`).** Both serve the same deployment, and zone features run only on the custom domain, so
  every page fetched from both must be byte-identical: any difference is Cloudflare changing pages (Rocket Loader, Email
  Obfuscation, minify, Automatic HTTPS Rewrites). Make the build emit what the zone would rewrite (an `http://purl.org`
  link differed until the source used https), and recheck once before calling a difference real (a deploy can land
  mid-run). No build artefact is needed, so it runs anywhere on a timer.
- **Hiding a rollback project from search without breaking the rollback (2026-11-19).** Put `X-Robots-Tag` in
  `_headers` under host rules (`https://<project>.pages.dev/*` and `https://:sub.<project>.pages.dev/*`, which covers
  branch aliases and new deployment hashes; verified). Never `<meta name="robots">`: it would deindex the real domain the
  moment it moves back. Keep robots.txt open so crawlers can see the noindex. Older deployment hashes keep their old
  headers (deployments are immutable).
- **Email Address Obfuscation (Scrape Shield, ON by default) breaks under Trusted Types.** On a proxied custom domain
  it rewrites every address to `[email protected]` + `/cdn-cgi/l/email-protection` and its decoder sets `innerHTML`,
  which `require-trusted-types-for 'script'` blocks, so addresses never come back (`*.pages.dev` is untouched, so
  previews look fine). Turn it off at launch (Security → Settings), or wrap addresses in `<!--email_off-->…<!--/email_off-->`.
- **Adding a `_worker.js` silently switches off `functions/` (williejackson.com, 2026-11-18).** Advanced mode runs
  only the Worker, so every Pages Function stops: the contact form's `functions/contact/send.js` answered 405 for 8
  hours after a publish added a Markdown-negotiation `_worker.js`, and no check noticed. Move each dynamic route into
  the Worker the same day, and make the post-deploy check POST to it (empty form → expect the 303 back, sends nothing).
- **The real Turnstile widget needs Trusted Types off on its page (williejackson.com, 2026-11-18).** Its `api.js` sets a
  `<script>`'s text, which `require-trusted-types-for 'script'` blocks: no token, every send fails "verify", and on a
  phone the button seems to do nothing. The always-pass TEST key never runs that code, so preview tests pass. Drop the
  TT line only on the form pages (`_headers`: `! Content-Security-Policy` then the CSP without it) and test the real key
  on the real domain; headless browsers get challenged, so the last proof is a person sending one message.
- **A zone-scoped token's reach.** The homelab's `CF_ZONE_TOKEN` reads DNS, custom firewall rules and
  page rules, but gets "not authorized" for redirect/cache/transform rulesets and "Authentication
  error" for zone settings.

## Accept-negotiated image Functions hand link-preview scrapers the original (2026-11-07, photo-site)

If a Pages Function picks AVIF/WebP derivatives from the `Accept` header and "falls back to
the original" otherwise, every `og:image` fetch takes the fallback: iMessage, Slack, Facebook
and Twitter scrapers send `Accept: */*` with no image types. On the photo site that meant a
2.8 MB, 6000 px JPEG behind each preview card while browsers got an 85 KB AVIF — under every
platform's size cap, so nothing failed, and a browser-shaped `curl` probe returned 200 and
looked fine. Two fixes, both needed: pre-generate one JPEG derivative per image (no on-the-fly
resize on Pages, see the first section) and serve it when no modern format is accepted; and
emit `og:image:width`/`height` so the first share renders full size. Verify as the scraper,
not the browser:

```bash
curl -s -A facebookexternalhit/1.1 -H 'Accept: */*' -o /tmp/og -w '%{content_type} %{size_download}B\n' "$OG_URL"
```

The edge cache keys on `Accept`, so a fix is invisible to any already-cached `og:image` URL
for its `max-age`; change the URL (a different `w=`) when the derivative set changes.

## Deleted pages, fresh deploys and advanced-mode Workers (2026-11-18, williejackson.com)

- **A deleted page can outlive its deploy by a week on the custom domain.** After the deploy without
  `/visiting-the-pal-jacksons/`, williejackson.com kept answering 200 with the old page (`age` growing,
  `cache-control: public, s-maxage=604800`, `cf-cache-status: DYNAMIC`) while the new deployment's own URL and any
  `?query` variant gave 404. Purge-by-URL and **purge everything** on the zone did not clear it: it is Pages' own per-URL
  cache. Fix that worked at once: an advanced-mode `_worker.js` that answers 410 for the path itself (mockups
  `scripts/agent/_worker.js`, `GONE` list). Old deployments also keep the file at their hash URLs; delete them via the API
  (`DELETE …/pages/projects/<p>/deployments/<id>?force=true`) when the content was private.
- **A fresh deployment URL 404s at random for a few minutes.** Right after `wrangler pages deploy`, parallel fetches of
  the new `<hash>.<project>.pages.dev` returned scattered 404s (a different set each run); a minute later all 200. Any
  post-deploy check must retry failures for several minutes before believing them (`wj-agent-check.py --settle 600`).
- **`_headers` and `_redirects` still apply to `env.ASSETS.fetch()` responses in advanced mode** (verified: CSP and
  security headers arrive on pages served through `_worker.js`), and Workers headers you `append()` merge with them.
- **`_routes.json` keeps assets off the Worker** (static requests stay free and unlimited); check the project's
  `deployment_configs.production.fail_open` via the API (true on both of Will's projects) before putting every page
  behind a Worker on the free plan: fail open serves the static asset when the 100k/day quota runs out.
- **Pages serves `.md` as `text/markdown; charset=utf-8`** by default. Cloudflare's zone "Markdown for Agents" needs a
  Pro plan; on Free, build-time `index.md` twins plus a negotiating `_worker.js` do the same.

## Related

- `wordpress-static-export`: a WordPress site exported to a Git-integrated Pages project.
- `photo-site-album-ingest`: the album workflow that produced the scraper finding above.

For Workers Cron Trigger gotchas (day-of-week numbering, testing
`scheduled()` against real bindings, subrequest-limit sizing) and R2
delete/rename verification, see the `cloudflare-workers-cron-email` skill —
distinct topic area, same "the platform did something non-obvious" theme.

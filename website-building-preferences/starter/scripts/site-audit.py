#!/usr/bin/env python3
"""site-audit.py: check a DEPLOYED site against Will's ship standard (specification.website, adopted 2026-11-05).

  python3 site-audit.py https://example.com [--preview] [--pages N] [--path /a/ --path /b/]
                        [--alias project.pages.dev] [--sitemap-check N] [--old-urls FILE]

Search-engine hygiene (Will, 2026-11-20: "demo and preview sites aren't going to show up in search engine results"):
every preview page must say noindex; on a launched site there is ONE indexable host: the other www/apex variant and
each --alias (the Pages project's own <project>.pages.dev, which Cloudflare does NOT mark noindex) must 301 to the same
path, every page's canonical is its own production URL, sitemap URLs answer 200 with no redirect, and each old URL in
--old-urls (one path per line, optional expected target after a space) lands on a live page in one hop.

Checks site-wide files and headers, then each page (homepage + up to N pages from the sitemap or homepage links).
Each line: PASS / FAIL / WARN / INFO plus the spec slug it comes from. Exit code 1 if any FAIL.
--preview: the site is a pre-launch preview, so noindex, robots Disallow and a missing sitemap are expected.
Standard library only. Read-only: GET/HEAD requests, nothing else.
"""
import argparse, json, re, struct, sys, urllib.request, urllib.error, urllib.parse
from html.parser import HTMLParser

UA = "site-audit/1.0 (+specification.website checklist)"
results = []

def rec(status, slug, msg):
    results.append((status, slug, msg)); print(f"{status:4} {slug:42} {msg}")

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None

def fetch(url, method="GET", follow=True, headers=None):
    h = {"User-Agent": UA, "Accept-Encoding": "br, gzip"} | (headers or {})
    req = urllib.request.Request(url, method=method, headers=h)
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        r = opener.open(req, timeout=20); return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read() if method == "GET" else b"", r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read() if method == "GET" else b"", url
    except Exception as e:
        return 0, {}, str(e).encode(), url

def body_text(status, hdrs, raw):
    enc = hdrs.get("content-encoding", "")
    if enc == "gzip":
        import gzip; raw = gzip.decompress(raw)
    elif enc == "br":  # stdlib has no brotli: refetch uncompressed
        return None
    return raw.decode("utf-8", "replace")

def get_text(url):
    s, h, b, final = fetch(url, headers={"Accept-Encoding": "identity"})
    return s, h, b.decode("utf-8", "replace"), final

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metas, self.links, self.imgs, self.scripts, self.headings, self.iframes = [], [], [], [], [], []
        self.title_parts, self.titles, self.in_title, self.in_head, self.html_attrs = [], 0, False, False, {}
        self.anchors, self._a, self.jsonld, self._ld = [], None, [], None; self.text_hrefs = []
    def handle_starttag(self, t, a):
        a = dict(a)
        if t == "html": self.html_attrs = a
        elif t == "head": self.in_head = True
        elif t == "title": self.in_title, self.titles = True, self.titles + 1
        elif t == "meta": self.metas.append(a)
        elif t == "link": self.links.append(a)
        elif t == "img": self.imgs.append(a)
        elif t == "iframe": self.iframes.append(a)
        elif t == "script":
            self.scripts.append((a, self.in_head))
            if a.get("type") == "application/ld+json": self._ld = []
        elif re.fullmatch(r"h[1-6]", t): self.headings.append(int(t[1]))
        elif t == "a": self._a = {"attrs": a, "text": "", "img_alt": ""}
        if self._a is not None and t == "img": self._a["img_alt"] += a.get("alt") or ""
    def handle_endtag(self, t):
        if t == "title": self.in_title = False
        elif t == "head": self.in_head = False
        elif t == "script" and self._ld is not None: self.jsonld.append("".join(self._ld)); self._ld = None
        elif t == "a" and self._a is not None: self.anchors.append(self._a); self._a = None
    def handle_data(self, d):
        if self.in_title: self.title_parts.append(d)
        if self._ld is not None: self._ld.append(d)
        if self._a is not None: self._a["text"] += d
    def meta(self, key, val):
        return [m.get("content", "") for m in self.metas if (m.get(key) or "").lower() == val.lower()]

def image_size(b):
    if b[:8] == b"\x89PNG\r\n\x1a\n": return "png", struct.unpack(">II", b[16:24])
    if b[:2] == b"\xff\xd8":
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF: i += 1; continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2): h, w = struct.unpack(">HH", b[i + 5:i + 9]); return "jpeg", (w, h)
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP": return "webp", None
    return "other", None

def audit_site(base, preview):
    root = base + "/"
    s, h, _, _ = fetch(base.replace("https://", "http://", 1) + "/", method="HEAD", follow=False)
    loc = h.get("location", "")
    rec("PASS" if s in (301, 308) and loc.startswith("https://") else "FAIL", "security/https-tls", f"http:// answers {s} -> {loc or 'no redirect'}")
    s, h, raw, _ = fetch(root)
    if s != 200: rec("FAIL", "foundations", f"homepage returned {s}"); return
    hsts = h.get("strict-transport-security", "")
    m = re.search(r"max-age=(\d+)", hsts)
    rec("PASS" if m and int(m.group(1)) >= 31536000 else "FAIL", "security/hsts", hsts or "missing")
    if "preload" in hsts or "includesubdomains" in hsts.lower(): rec("INFO", "security/hsts", "includeSubDomains/preload set: confirm it was Will's per-domain decision")
    csp = h.get("content-security-policy", "")
    rec("PASS" if csp else "WARN", "security/content-security-policy", (csp[:90] + "…") if len(csp) > 90 else (csp or "missing"))
    # A template that HTML-escapes the policy ('self' -> &#39;self&#39;) ships a header browsers can't parse: every
    # source is then blocked (j2wtalent 2026-11-19: fonts, icons and manifest refused, while this check said PASS).
    if re.search(r"&#\d+;|&quot;|&amp;", csp): rec("FAIL", "security/content-security-policy", "policy is HTML-escaped (&#39; etc.): browsers can't parse it")
    fa = "frame-ancestors" in csp or h.get("x-frame-options", "").upper() in ("DENY", "SAMEORIGIN")
    rec("PASS" if fa else "FAIL", "security/frame-ancestors", "frame-ancestors in CSP" if "frame-ancestors" in csp else (h.get("x-frame-options") or "missing"))
    rec("PASS" if h.get("x-content-type-options", "").lower() == "nosniff" else "FAIL", "security/x-content-type-options", h.get("x-content-type-options", "missing"))
    for name, slug in (("referrer-policy", "security/referrer-policy"), ("permissions-policy", "security/permissions-policy"), ("cross-origin-opener-policy", "security/cross-origin-isolation")):
        rec("PASS" if h.get(name) else "WARN", slug, h.get(name, "missing")[:80])
    if "x-xss-protection" in h: rec("FAIL", "security/x-xss-protection", "header present (spec: avoid)")
    rec("PASS" if "require-trusted-types-for" in csp else "WARN", "security/trusted-types", "require-trusted-types-for in CSP" if "require-trusted-types-for" in csp else "not enforced")
    rec("PASS" if h.get("content-encoding") in ("br", "gzip", "zstd") else "FAIL", "performance/compression", h.get("content-encoding", "none"))
    rec("PASS" if "h3" in h.get("alt-svc", "") else "WARN", "performance/http3", h.get("alt-svc", "no alt-svc")[:40])
    cc = h.get("cache-control", "")
    rec("PASS" if cc else "FAIL", "performance/cache-control", f"HTML: {cc or 'missing'}")
    xr = h.get("x-robots-tag", "")
    if "noindex" in xr: rec("INFO" if preview else "FAIL", "seo/meta-robots", f"X-Robots-Tag: {xr}" + (" (expected on a preview)" if preview else " on a launched site"))
    # robots.txt
    s, rh, rb, _ = get_text(root + "robots.txt")
    if s != 200: rec("FAIL", "seo/robots-txt", f"/robots.txt {s}")
    else:
        rec("PASS", "seo/robots-txt", rh.get("content-type", "")[:30])
        disallow_all = re.search(r"(?mi)^user-agent:\s*\*\s*$(?:\n(?!user-agent).*)*\n\s*disallow:\s*/\s*$", rb)
        if disallow_all: rec("INFO" if preview else "FAIL", "seo/robots-txt", "User-agent: * Disallow: /" + (" (preview)" if preview else ""))
        if not preview:
            rec("PASS" if re.search(r"(?mi)^sitemap:\s*https://", rb) else "FAIL", "seo/xml-sitemaps", "Sitemap: line in robots.txt")
            rec("PASS" if re.search(r"(?mi)^content-signal:", rb) else "WARN", "agent-readiness/content-signals", "Content-Signal line")
            train = [b for b in ("GPTBot", "ClaudeBot", "Google-Extended", "CCBot", "Applebot-Extended") if re.search(rf"(?mi)^user-agent:\s*{b}\s*$\n\s*disallow:\s*/\s*$", rb)]
            rec("PASS" if len(train) == 5 else "WARN", "agent-readiness/robots-for-ai-crawlers", f"training bots blocked: {', '.join(train) or 'none'} (Will's default: block training, allow AI search)")
    if not preview:
        for p in ("sitemap.xml", "sitemap-index.xml"):
            s, sh, sb, _ = get_text(root + p)
            if s == 200: rec("PASS", "seo/xml-sitemaps", f"/{p} {sb.count('<loc>')} URLs"); break
        else: rec("FAIL", "seo/xml-sitemaps", "no /sitemap.xml or /sitemap-index.xml")
    s, _, lb, _ = get_text(root + "llms.txt")
    rec("PASS" if s == 200 and lb.lstrip().startswith("#") else "WARN", "agent-readiness/llms-txt", f"/llms.txt {s}")
    for p, slug in (("favicon.ico", "foundations/favicons"), ("apple-touch-icon.png", "foundations/favicons")):
        s, ih, _, _ = fetch(root + p, method="HEAD")
        rec("PASS" if s == 200 and "image" in ih.get("content-type", "") else "WARN", slug, f"/{p} {s} {ih.get('content-type', '')}")
    s, nh, nb, _ = get_text(root + "this-page-should-not-exist-7f3a/")
    rec("PASS" if s == 404 else "FAIL", "resilience/error-pages", f"missing page returns {s}" + (" (soft 404: spec says avoid)" if s == 200 else ""))
    if s == 404 and ("<main" not in nb or len(nb) < 300): rec("WARN", "resilience/error-pages", "404 body looks bare: give it the site's header, footer and a way home")
    s, _, sb, _ = get_text(root + ".well-known/security.txt")
    rec("PASS" if s == 200 and "Contact:" in sb else "INFO", "security/security-txt", f"{s} (Will skipped security.txt 2026-11-05)" if s != 200 else "present")
    return raw

def audit_page(url, preview):
    s, h, html, final = get_text(url)
    if s != 200: rec("FAIL", "page", f"{url} returned {s}"); return []
    path = urllib.parse.urlparse(url).path or "/"
    p = Page(); p.feed(html); L = lambda st, slug, msg: rec(st, slug, f"{path}: {msg}")
    L("PASS" if re.match(r"(?is)\s*<!doctype html>", html) else "FAIL", "foundations/doctype", "first line" )
    L("PASS" if p.html_attrs.get("lang") else "FAIL", "foundations/html-lang", p.html_attrs.get("lang", "missing"))
    L("PASS" if re.search(rb'(?i)<meta[^>]+charset=["\']?utf-8'.decode(), html[:1024]) else "FAIL", "foundations/meta-charset", "utf-8 in first 1024 bytes")
    vp = p.meta("name", "viewport")
    L("PASS" if vp and not re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", vp[0]) else "FAIL", "foundations/meta-viewport", vp[0] if vp else "missing")
    title = "".join(p.title_parts).strip()
    L("PASS" if p.titles == 1 and title else "FAIL", "foundations/title", f"{p.titles} title(s): {title[:60]!r}")
    d = p.meta("name", "description")
    L("PASS" if d and 50 <= len(d[0]) <= 170 else "WARN", "foundations/meta-description", f"{len(d[0]) if d else 0} chars")
    canon = [l.get("href") for l in p.links if (l.get("rel") or "").lower() == "canonical"]
    L("PASS" if canon and canon[0].startswith("https://") else "WARN", "foundations/canonical-url", canon[0] if canon else "missing")
    if len(canon) > 1: L("FAIL", "foundations/canonical-url", f"{len(canon)} canonical links")
    if canon:
        cu, fu = urllib.parse.urlparse(canon[0]), urllib.parse.urlparse(final)
        if cu.path != fu.path:
            L("FAIL", "seo/canonical-self", f"canonical names another page: {canon[0]} (this is {fu.path})")
        elif preview and (cu.netloc == fu.netloc or cu.netloc.endswith(".pages.dev")):
            L("WARN", "seo/canonical-self", f"canonical names a preview host {cu.netloc}: point it at production")
        elif not preview and cu.netloc != fu.netloc:
            L("FAIL", "seo/canonical-self", f"canonical host {cu.netloc} is not the site's host {fu.netloc}")
        else: L("PASS", "seo/canonical-self", "canonical is this page's production URL")
    if not preview and final.split("#")[0] != url.split("#")[0]:
        L("FAIL", "seo/one-hop", f"{url} redirected to {final}: link and list the final URL")
    robots = " ".join(p.meta("name", "robots")).lower()
    if "noindex" in robots: L("INFO" if preview else "FAIL", "seo/meta-robots", f"meta robots {robots}")
    if preview:
        xr = h.get("x-robots-tag", "").lower()
        L("PASS" if "noindex" in xr or "noindex" in robots else "FAIL", "seo/preview-noindex",
          "noindex (" + ("header" if "noindex" in xr else "meta") + ")" if "noindex" in xr or "noindex" in robots else "a preview page search engines may index: send X-Robots-Tag noindex")
    elif path != "/":
        alt = path[:-1] if path.endswith("/") else path + "/"
        s2, h2, _, _ = fetch(urllib.parse.urljoin(url, alt), method="HEAD", follow=False)
        loc = urllib.parse.urljoin(url, h2.get("location", ""))
        L("PASS" if s2 in (301, 308) and loc.rstrip("/") == final.rstrip("/") or s2 == 404 else "WARN", "seo/duplicate-urls",
          f"{alt} answers {s2}" + (f" -> {h2.get('location')}" if h2.get("location") else "") + (" (a duplicate of this page)" if s2 == 200 else ""))
    og = {k: (p.meta("property", "og:" + k) or [""])[0] for k in ("title", "description", "url", "type", "image", "image:alt", "image:width", "image:height", "site_name")}
    missing = [k for k in ("title", "description", "url", "type", "image") if not og[k]]
    L("PASS" if not missing else "FAIL", "foundations/open-graph", "complete" if not missing else f"missing og:{', og:'.join(missing)}")
    if og["url"] and canon and og["url"] != canon[0]: L("WARN", "foundations/open-graph", f"og:url {og['url']} != canonical")
    if og["image"]:
        if not og["image"].startswith("https://"): L("FAIL", "foundations/open-graph", f"og:image not absolute: {og['image']}")
        else:
            # A preview's og:image names the production host (absolute URLs are built from site.url): fetch the same
            # path from the preview instead, or a pre-launch site fails on a file the old site doesn't have (2026-11-19).
            img = og["image"]
            if preview:
                u = urllib.parse.urlparse(url); img = f"{u.scheme}://{u.netloc}" + urllib.parse.urlparse(img).path
            si, ih, ib, _ = fetch(img, headers={"Accept-Encoding": "identity"})
            kind, dims = image_size(ib[:65536]) if si == 200 else ("none", None)
            ok = si == 200 and kind in ("jpeg", "png") and dims and dims[0] >= 1200 and dims[1] >= 630
            L("PASS" if ok else "FAIL", "foundations/open-graph", f"og:image {si} {kind} {dims} (want JPG/PNG >= 1200x630)")
            corp = ih.get("cross-origin-resource-policy", "")
            if corp in ("same-origin", "same-site"): L("WARN", "foundations/open-graph", f"og:image sends CORP {corp}: other sites may not load it")
        if not og["image:alt"]: L("WARN", "foundations/open-graph", "no og:image:alt")
    L("PASS" if p.meta("name", "twitter:card") else "WARN", "foundations/open-graph", f"twitter:card {(p.meta('name', 'twitter:card') or ['missing'])[0]}")
    L("PASS" if p.meta("name", "theme-color") else "WARN", "foundations/theme-color", (p.meta("name", "theme-color") or ["missing"])[0])
    L("PASS" if p.meta("name", "color-scheme") else "WARN", "foundations/color-scheme", (p.meta("name", "color-scheme") or ["missing"])[0])
    rels = [(l.get("rel") or "").lower() for l in p.links]
    L("PASS" if "icon" in rels and "apple-touch-icon" in rels and "manifest" in rels else "WARN", "foundations/favicons", f"icon={'icon' in rels} apple-touch={'apple-touch-icon' in rels} manifest={'manifest' in rels}")
    feeds = [l for l in p.links if (l.get("rel") or "").lower() == "alternate" and "xml" in (l.get("type") or "")]
    L("PASS" if feeds else "INFO", "foundations/feed-discovery", feeds[0].get("href") if feeds else "no RSS/Atom link (needed on sites that publish)")
    for i, j in enumerate(p.jsonld):
        try:
            data = json.loads(j); types = [n.get("@type") for n in data.get("@graph", [data])]
            L("PASS", "seo/structured-data", f"JSON-LD {types}")
        except Exception as e: L("FAIL", "seo/structured-data", f"JSON-LD block {i} does not parse: {e}")
    if not p.jsonld: L("WARN", "seo/structured-data", "no JSON-LD")
    h1 = p.headings.count(1)
    L("PASS" if h1 == 1 else "FAIL", "seo/heading-hierarchy", f"{h1} h1")
    skips = [f"h{a}->h{b}" for a, b in zip(p.headings, p.headings[1:]) if b > a + 1]
    L("PASS" if not skips else "FAIL", "seo/heading-hierarchy", "no skipped levels" if not skips else f"skips {sorted(set(skips))}")
    noalt = [i.get("src", "?")[-40:] for i in p.imgs if "alt" not in i]
    L("PASS" if not noalt else "FAIL", "accessibility/image-alt-text", f"{len(p.imgs)} img, {len(noalt)} without alt {noalt[:3]}")
    nodim = [i.get("src", "?")[-40:] for i in p.imgs if not (i.get("width") and i.get("height"))]
    L("PASS" if not nodim else "WARN", "performance/core-web-vitals", f"{len(nodim)} img without width/height {nodim[:3]}")
    modern = len(re.findall(r'<source[^>]+type="image/(?:avif|webp)"', html)) + sum(1 for i in p.imgs if re.search(r"\.(avif|webp)(\?|$)", i.get("src", "")))
    photos = [i for i in p.imgs if re.search(r"\.(jpe?g|png)(\?|$)", i.get("src", ""), re.I)]
    if photos and not modern: L("WARN", "performance/image-optimization", f"{len(photos)} JPG/PNG img with no AVIF/WebP source (use the eleventy-img transform)")
    elif p.imgs: L("PASS", "performance/image-optimization", f"AVIF/WebP sources present ({modern})")
    lazy_first = p.imgs and p.imgs[0].get("loading") == "lazy"
    if lazy_first: L("WARN", "performance/lazy-loading", "first image is lazy (LCP candidate should not be)")
    blocking = [a.get("src") for a, in_head in p.scripts if in_head and a.get("src") and not ({"defer", "async"} & set(a)) and a.get("type") != "module"]
    L("PASS" if not blocking else "FAIL", "performance/script-loading", "no render-blocking scripts" if not blocking else f"blocking: {blocking}")
    # Zone features that rewrite HTML on a Cloudflare custom domain (never on pages.dev). Under Trusted Types, Rocket
    # Loader stops every script and Email Obfuscation leaves "[email protected]" (williejackson.com launch, 2026-11-18).
    rewritten = [n for n, pat in (("Rocket Loader", r'rocket-loader|type="[0-9a-f]+-text/javascript"'), ("Email Obfuscation", r"cdn-cgi/l/email-protection")) if re.search(pat, html)]
    L("FAIL" if rewritten else "PASS", "resilience/edge-rewriting", f"Cloudflare is rewriting the page: {', '.join(rewritten)} (zone setting; turn it off or add data-cfasync=\"false\" / <!--email_off-->)" if rewritten else "served without Rocket Loader or Email Obfuscation rewriting")
    L("PASS" if any(a.get("type") == "speculationrules" for a, _ in p.scripts) else "INFO", "performance/speculation-rules", "speculation rules present" if any(a.get("type") == "speculationrules" for a, _ in p.scripts) else "none")
    empty = [a["attrs"].get("href", "")[-40:] for a in p.anchors if not (a["text"].strip() or a["img_alt"].strip() or a["attrs"].get("aria-label") or a["attrs"].get("title"))]
    L("PASS" if not empty else "FAIL", "accessibility/empty-links-buttons", f"{len(empty)} links with no accessible text {empty[:3]}")
    vague = [a["text"].strip() for a in p.anchors if a["text"].strip().lower() in ("click here", "here", "read more", "more", "link")]
    if vague: L("WARN", "accessibility/link-text", f"vague link text {sorted(set(vague))}")
    skip = any((a["attrs"].get("href") or "").startswith("#") and "skip" in (a["text"] + a["attrs"].get("class", "")).lower() for a in p.anchors[:5])
    L("PASS" if skip else "WARN", "accessibility/skip-links", "skip link near the top" if skip else "no skip link among the first 5 links")
    untitled = [f.get("src", "?")[:40] for f in p.iframes if not f.get("title")]
    if untitled: L("FAIL", "accessibility/semantic-html", f"iframes without title {untitled}")
    if path == "/":
        priv = [a for a in p.anchors if "privacy" in (a["attrs"].get("href") or "").lower()]
        L("PASS" if priv else ("WARN" if preview else "FAIL"), "privacy/privacy-policy", f"links to {priv[0]['attrs']['href']}" if priv else "no link to a privacy page")
    for tag in ("<main", "<nav", "<footer"):
        if tag not in html: L("WARN", "accessibility/semantic-html", f"no {tag}>")
    return [urllib.parse.urljoin(url, a["attrs"].get("href", "")) for a in p.anchors]

def no_follow(url):
    s, h, _, _ = fetch(url, method="HEAD", follow=False)
    return s, (urllib.parse.urljoin(url, h["location"]) if h.get("location") else ""), h

def audit_indexing(base, preview, aliases, locs, limit, old_urls):
    """One indexable host, previews noindex, sitemap and old URLs one hop (Will, 2026-11-20)."""
    host = urllib.parse.urlparse(base).netloc
    if preview:
        for a in aliases: rec("INFO", "seo/one-host", f"--alias {a} ignored on a preview")
        return
    other = host[4:] if host.startswith("www.") else "www." + host
    s, loc, _ = no_follow(f"https://{other}/")
    if s == 0: rec("INFO", "seo/one-host", f"{other} does not answer (fine: nothing to index)")
    else: rec("PASS" if s in (301, 308) and loc.rstrip("/") == base else "FAIL", "seo/one-host", f"https://{other}/ answers {s}" + (f" -> {loc}" if loc else " (a second indexable copy)"))
    for a in aliases:
        probe = "/" + (urllib.parse.urlparse(locs[1]).path.lstrip("/") if len(locs) > 1 else "")
        s, loc, h = no_follow(f"https://{a}{probe}")
        want = base + probe
        if s in (301, 308) and loc.rstrip("/") == want.rstrip("/"): rec("PASS", "seo/one-host", f"{a}{probe} -> {loc}")
        elif "noindex" in h.get("x-robots-tag", "").lower(): rec("WARN", "seo/one-host", f"{a} is noindex but not redirected: a 301 passes credit to {host}, noindex doesn't")
        elif s in (301, 308): rec("FAIL", "seo/one-host", f"{a}{probe} answers {s} -> {loc}, not {want}")
        else: rec("FAIL", "seo/one-host", f"{a}{probe} answers {s}: an indexable copy of the site (301 it: starter functions/_middleware.js)")
    if not aliases: rec("WARN", "seo/one-host", "no --alias given: name the Pages project's <project>.pages.dev so it is checked")
    pages = [l for l in locs if not l.endswith(".xml")][:limit]
    if pages:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(4) as ex: res = list(ex.map(lambda u: (u, no_follow(u)), pages))
        off = [u for u in pages if urllib.parse.urlparse(u).netloc != host]
        bad = [f"{urllib.parse.urlparse(u).path} {r[0]}" for u, r in res if r[0] != 200]
        rec("PASS" if not bad and not off else "FAIL", "seo/xml-sitemaps", f"{len(pages)} sitemap URLs answer 200 with no redirect" if not bad and not off else f"{len(bad)} not 200 {bad[:5]}, {len(off)} on another host {off[:2]}")
    if old_urls:
        bad, n = [], 0
        for line in open(old_urls):
            parts = line.split()
            if not parts or parts[0].startswith("#"): continue
            n += 1; u = urllib.parse.urljoin(base + "/", parts[0])
            s, loc, _ = no_follow(u)
            if s in (301, 308):
                s2, _, _ = no_follow(loc)
                ok = s2 == 200 and (len(parts) < 2 or loc.rstrip("/") == urllib.parse.urljoin(base + "/", parts[1]).rstrip("/"))
            else: ok = s == 200 and len(parts) < 2
            if not ok: bad.append(f"{parts[0]} {s}{' -> ' + loc if loc else ''}")
        rec("PASS" if not bad else "FAIL", "seo/old-urls", f"{n} old URLs land on a live page in one hop" if not bad else f"{len(bad)}/{n} don't: {bad[:5]}")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("url"); ap.add_argument("--preview", action="store_true")
    ap.add_argument("--pages", type=int, default=6); ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--alias", action="append", default=[], help="another host serving this site (e.g. project.pages.dev): must 301 here")
    ap.add_argument("--sitemap-check", type=int, default=300, help="sitemap URLs to check for 200-without-redirect (0 = skip)")
    ap.add_argument("--old-urls", help="file of old paths (optional expected target after a space): each must land live in one hop")
    a = ap.parse_args(); base = a.url.rstrip("/")
    print(f"== site: {base}" + (" (preview)" if a.preview else ""))
    audit_site(base, a.preview)
    if a.path:
        for u in [base + "/"] + [base + p for p in a.path]: print(f"== page: {u}"); audit_page(u, a.preview)
        print("== indexing"); audit_indexing(base, a.preview, a.alias, [], 0, a.old_urls)
        return summary()
    locs = []
    for p in ("/sitemap.xml", "/sitemap-index.xml"):
        s, _, sm, _ = get_text(base + p)
        if s == 200: locs = re.findall(r"<loc>([^<]+)</loc>", sm); break
    if locs and all(l.endswith(".xml") for l in locs):  # a sitemap index: take pages from its first child sitemaps
        kids = locs; locs = []
        for k in kids[:3]: locs += re.findall(r"<loc>([^<]+)</loc>", get_text(k)[2])
    # Sitemap URLs name the production host; on a preview, audit the same paths on the preview, not the live site
    # (j2wtalent 2026-11-19: the old live site's pages were audited instead of the rebuild).
    locs = [base + urllib.parse.urlparse(l).path if not l.endswith(".xml") else l for l in locs] if a.preview else locs
    print(f"== page: {base}/"); links = audit_page(base + "/", a.preview)
    if not locs:  # no sitemap (e.g. a preview): follow the homepage's own links
        locs = [l for l in dict.fromkeys(links) if l.startswith(base + "/") and "#" not in l
                and not re.search(r"\.(xml|txt|jpg|png|webp|avif|svg|pdf|js|css|ico|webmanifest)$", l)]
    for u in [l for l in locs if l.rstrip("/") != base][:a.pages]: print(f"== page: {u}"); audit_page(u, a.preview)
    print("== indexing"); audit_indexing(base, a.preview, a.alias, locs, a.sitemap_check, a.old_urls)
    return summary()

def summary():
    c = {k: sum(1 for r in results if r[0] == k) for k in ("PASS", "FAIL", "WARN", "INFO")}
    print(f"\n{c['PASS']} pass, {c['FAIL']} fail, {c['WARN']} warn, {c['INFO']} info")
    for st, slug, msg in results:
        if st == "FAIL": print(f"  FAIL {slug}: {msg}")
    return 1 if c["FAIL"] else 0

if __name__ == "__main__": sys.exit(main())

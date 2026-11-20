// The Pages project's own production address (<project>.pages.dev) 301s to the custom domain (Will, 2026-11-20).
// Cloudflare marks only PREVIEW deployments noindex; the project's pages.dev host serves production with whatever
// headers the site sends, so after launch it is a second, indexable copy. Google ranked j2wstrategies-com.pages.dev
// for Will's name that way; a 301 passes the credit to the real domain, noindex doesn't.
// Branch and hash previews (<x>.<project>.pages.dev) and the custom domain pass through untouched.
// Fill CANONICAL at launch (same host as site.url). Until then this does nothing.
// public/_routes.json keeps static files out of Functions (cost and speed); site-audit.py --alias proves it works.
const CANONICAL = "[REPLACE: example.com]";

export async function onRequest({ request, next }) {
  const url = new URL(request.url);
  if (!CANONICAL.startsWith("[") && /^[^.]+\.pages\.dev$/.test(url.hostname)) {
    url.protocol = "https:"; url.hostname = CANONICAL; url.port = "";
    return Response.redirect(url.toString(), 301);
  }
  return next();
}

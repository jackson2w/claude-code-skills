// One place for everything the head, feeds, robots.txt, llms.txt and JSON-LD need. Fill every [BRACKET].
export default {
  name: "[Site name]",
  url: "https://example.com",           // [REPLACE] no trailing slash; absolute URLs (og:image, canonical) are built from it
  description: "[150–160 characters: what the site is, for whom]",
  lang: "en-US", locale: "en_US",
  author: { name: "Willie Jackson", url: "https://williejackson.com" },   // Will's entity name (preferences §0)
  publisher: "person",                  // "person" (Will's own sites) or "organization" (a magazine, a business)
  org: { name: "[Org name]", logo: "/icons/icon-512.png" },              // used when publisher = "organization"
  themeColor: "#ffffff",                // hex: the page background. theme-color must match what the browser chrome sits on
  colorScheme: "light",                 // "light", or "light dark" if the CSS really supports both
  ogImage: "/img/og/default.jpg",       // 1200x630 JPG; scripts/og-crop.cjs makes one from any photo
  ogImageAlt: "[describe the share image]",
  feed: "/feed.xml",                    // null on a site that doesn't publish posts
  // Privacy page (privacy/privacy-policy, Required). Will, 2026-11-05: published by "Willie Jackson", contact
  // security@jackson2w.com, no postal address. Change `updated` whenever the page's facts change.
  privacy: { controller: "Willie Jackson", contact: "security@jackson2w.com", updated: "2026-11-05" },
  // false until launch day: every page noindex, robots.txt Disallow, caching off (see public/_headers)
  launched: false,
  // Self-hosted fonts, subset and given metric-matched fallbacks by scripts/fonts.mjs. Originals in src/fonts-src/.
  // fallback: a @capsizecss/metrics name (arial, helvetica, georgia, timesNewRoman, …) close to the font's shape.
  // preload: only the font the first screen of body text uses (one, maybe two).
  fonts: [
    // { family: "IBM Plex Sans", file: "IBMPlexSans-Var.ttf", weight: "100 700", style: "normal", fallback: "arial", preload: true },
  ],
  fontExtraText: "",                    // characters beyond Latin that pages use (check-glyphs.mjs tells you)
  // Cloudflare Web Analytics (free, cookieless, real visitors' Core Web Vitals). Launch checklist: create the site in
  // the dashboard (Analytics & Logs → Web Analytics → Add a site → manual JS snippet), paste the token here.
  analyticsToken: null,
  // AI crawlers (Will, 2026-11-05): allow AI search and answers, block training. Search engines always allowed.
  ai: { search: "yes", aiInput: "yes", aiTrain: "no" },
};

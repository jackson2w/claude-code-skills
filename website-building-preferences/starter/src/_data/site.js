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
  // false until launch day: every page noindex, robots.txt Disallow, caching off (see public/_headers)
  launched: false,
  // AI crawlers (Will, 2026-11-05): allow AI search and answers, block training. Search engines always allowed.
  ai: { search: "yes", aiInput: "yes", aiTrain: "no" },
};

---
name: wikipedia-wikidata
description: This skill should be used when helping Will (or someone he's helping) with Wikidata items or Wikipedia articles — creating a Wikidata item for a person, organization or publication; walking a human through the Wikidata editing UI; linking a website to its Wikidata item via schema.org sameAs; making a site's articles cite cleanly in Wikipedia's citation tool (Citoid); judging whether a person meets Wikipedia notability; helping save an article at Articles for Deletion (AfD); or researching someone's public footprint for references. Built 2026-11-08/09 (Abernathy Q142086921, Will Q142087430, Deepa Purushothaman's AfD). Trigger phrases include "wikidata", "wikidata item", "Q-number", "QID", "sameAs wikidata", "wikipedia article", "wikipedia deletion", "articles for deletion", "AfD", "notability", "WP:GNG", "WP:NBIO", "WP:NAUTHOR", "reliable sources", "conflict of interest wikipedia", "COI disclosure", "Edit COI", "citoid", "cite web", "wikipedia citation", "references for wikipedia", "press links for wikipedia", "find sources about me", "public footprint".
---

# Wikipedia and Wikidata

The work here is research and verification by Claude, editing by the human. Will (or the subject) makes
every Wikidata/Wikipedia edit under their own account, with any conflict of interest disclosed; Claude
drafts exact text, then **verifies each step through the public APIs** and reports what saved.

## 1. Wikidata items (a human edits; Claude drafts and checks)

**Before drafting:** search for an existing item (`wbsearchentities`), and **resolve every QID with
`wbgetentities` before it goes in a draft.** A peer agent once handed Will "online magazine (Q1151850)";
Q1151850 is the quadratic sieve. Correct one is Q847906.

```bash
UA="abernathy-site-check/1.0 (claude@williejackson.com)"   # Wikimedia wants a descriptive UA; space calls ~2 s apart or they return empty
curl -s -A "$UA" "https://www.wikidata.org/w/api.php?action=wbsearchentities&search=Harlem&language=en&limit=5&format=json"
curl -s -A "$UA" "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q847906%7CP740&props=labels%7Cdescriptions&languages=en&format=json"
curl -s -A "$UA" "https://www.wikidata.org/wiki/Special:EntityData/Q142086921.json"   # verify a saved item: claims, qualifiers, references
```

**The UI confusions Will hit, in order, and the one-line rule for each** (put these at the top of any
instructions):
- Pasting a URL into a reference's *left* box → "No match was found". The left box is the property:
  **reference URL** (P854); the link goes in the right box.
- Typing statement names (inception, named after…) as rows *inside one reference*. Each statement gets
  its own reference, added under that statement.
- Adding the other statements as **qualifiers** of "instance of" (they sit above "+ add qualifier").
  New facts are **+ add statement** (bottom of the page, outside every box); a second value of the
  same fact is **+ add value**; a source is **+ add reference** (below "N references").
- A link added via "+ add qualifier" instead of "+ add reference" → lightning-bolt "property scope
  constraint". Fix: edit, remove the row, re-add via + add reference.
- Several URLs in one reference: works, but one URL per reference is the norm.
- Write "Q-numbers" in parentheses next to each value; the dropdown matches namesakes ("Harlem" also
  matches a Polish band; there are ~10 Willie Jacksons).

**Constraint flags that are right to fix:** official website (P856) wants qualifier language of work
or name (P407); headquarters location (P159) wants a separate top-level **country** (P17) statement,
not a qualifier. Flags are suggestions, not errors.

**COI:** post on the item's Discussion tab ("Add topic"), subject "Conflict of interest disclosure",
one plain sentence. Wikidata asks for disclosure, not abstention.

**Useful IDs (verified 2026-11-08):** human Q5; online magazine Q847906; writer Q36180; publisher
Q2516866; consultant Q15978655; facilitator Q1150166; conference speaker Q100742049 (Wikidata's own
note on "orator" Q12859263 says use this); Florida State University Q861548 + academic major P812 →
information technology Q11661; Harlem Q189074; Oakland Q17042; US Q30; English Q1860; Ralph Abernathy
Q545488; African-American men Q106353292; The Hollywood Reporter Q61503; Yerba Buena Center for the Arts
Q1884883. Properties: P31, P106, P69, P27, P856, P6634 (LinkedIn ID), P551 residence, P112 founder,
P571 inception, P576 dissolved, P159 HQ, P740 location of formation, P138 named after, P921 main subject,
P407, P495, P17, P166 award (needs an item for the award; "YBCA 100" has none), P854 reference URL,
P248 stated in, P577 publication date. No items exist for ReadySet, W3 EDGE, altMBA, The Domino Project
(Q138724173 "Domino Project" is a Czech association) or Jackson Talent Strategies.

**Live items:** Abernathy Q142086921; Willie Jackson Q142087430 (Will's account: Christmasfrog99).

## 2. Linking a site to its item

schema.org JSON-LD `sameAs: ["https://www.wikidata.org/wiki/Q…"]` on the Organization/Person, and the
item's official website (P856) pointing back, so each confirms the other.
- abernathymagazine.com: Organization sameAs from `src/_data/site.js` (home + About); Will's Person
  sameAs in `src/_data/abernathyBrowse.js`. **Gotcha:** `abm-bs-jsonld.njk` reuses the name `site` for
  the URL string, shadowing the global data; it reads `siteData` instead. A wired-up check silently
  rendered nothing until the Q-number didn't appear live.
- williejackson.com (static export of private WordPress): homelab-ansible `wordpress-install.yml` task
  "Person JSON-LD" → mu-plugin `wj-person-jsonld.php` (home + About). A plugin change is not a content
  change, so the 5-min publisher ignores it: write `/var/lib/wp-static/flags/publish-requested` as the
  web user (what the Publish button does).
- Verify by parsing the live page's `application/ld+json`, not by grepping the source.

## 3. Citations from a site (Citoid)

Wikipedia's citation tool ignores JSON-LD authors and scrapes the visible byline. Test against the real
tool: `curl https://en.wikipedia.org/api/rest_v1/data/citation/mediawiki/<urlencoded URL>`, **on a preview
and on the live domain** (the custom domain fell back to a simpler scraper). What works: Dublin Core
(`DC.creator` "Last, First", `DC.date`, `DC.publisher`) plus `<meta name="author">` in natural order with
no degree or Jr./II/III. Not Highwire `citation_*` (turns every post into a journal article with no
journal). Detail and the 11ty filters: `website-building-preferences` §9.

## 4. Wikipedia notability and Articles for Deletion

**What counts** (WP:GNG / WP:NBIO): reliable + independent + significant coverage *of the person*. For an
author, WP:NAUTHOR #3: a work that is "the subject of multiple independent periodical articles or
reviews" — trade and newspaper reviews (Publishers Weekly, FT, Booklist, Kirkus, newspapers) are the
usual winning route. A syndicated review column counts once, however many papers ran it.

**What editors discount** (say so plainly when grading someone's list): as-told-to essays and Q&As;
rewrites of the subject's own essay or LinkedIn post (Indian aggregators did this for Deepa); bios from
employers, schools, fellowships and speaker bureaus (fine for plain facts, not notability); Forbes
`/sites/` contributor posts (WP:FORBESCON); passing quotes; sponsored or partner content (TIME.com's
"Charter" section says "created by Charter, independently from the TIME editorial staff" — cite Charter);
trivia about short-lived ventures ("opening and closing" coverage, per Bearian).

**Reading an AfD:** opened date + 7 days is the earliest close (often later; quiet ones get relisted).
```bash
curl -s -A "$UA" "https://en.wikipedia.org/w/api.php?action=query&prop=revisions&titles=Wikipedia:Articles_for_deletion/<Name>&rvprop=content|timestamp|user&rvslots=main&format=json"
curl -s -A "$UA" "https://en.wikipedia.org/w/api.php?action=query&list=exturlusage&euquery=<domain>&eunamespace=0&format=json"   # who links a domain
```

**COI etiquette for a friend helping:** disclose ("I know X personally"), post a **Comment** with sources
rather than a Keep !vote, never edit the article, never recruit others (canvassing). Propose a rewrite on
the article Talk page under `{{Edit COI}}` with the draft in `<pre>` — the request queue is very long
(1,485 on 2026-11-09), so also **reply to the engaged editor in the AfD with `{{ping|User}}`**, which is
the route that acts in time. A short, review-centred version ("less is more") answers "buried in trivia".

**Wikitext forms:** top-level `*'''Comment''' – …`; sub-bullets `**`; continuation `:`; reply to a `*`
entry with `*:`; sign with `~~~~`. Paste at the end of the AfD's edit box; Preview, then Publish.

## 5. Researching a public footprint

- Pull the CV first (their About pages, speaker bios), then search **name × every role, employer, place,
  school and title**, plus the person's own leads. Split into parallel researchers by career phase; brief
  each with the namesake list and the source tiers above; require them to open every page and quote it.
- Spot-check every researcher's top finds yourself before reporting (all held up both times, but the
  check also caught a sponsored label and a stale date).
- **Rules:** no archive copies of paywalled pages; no pushing a browser through bot walls (the
  permission classifier blocks it). JavaScript-only pages are fine to render; bot-walled or paywalled
  pages → ask the human for a PDF (File → Print → Save as PDF). Free pages that are now dead → Wayback.
- **Render a JS page** (dev box has Playwright/Chromium; claude-code has no Node):
  `scp scripts/pagetext.mjs dev@192.168.50.59:/tmp/pt/` once, with `mkdir -p /tmp/pt/node_modules &&
  ln -sfn $(npm root -g)/playwright /tmp/pt/node_modules/playwright`, then
  `node /tmp/pt/pagetext.mjs <url> '<regex>' 300`.
- **Read a PDF** the Read tool can't (it needs pdftoppm for big files; claude-code has no poppler, pypdf
  or pip): copy it to dev, `npm i pdfjs-dist@4.10.38` in /tmp/pt, `node pdftext.mjs file.pdf`.
- Podcasts: Apple's lookup API lists episodes with dates —
  `https://itunes.apple.com/lookup?id=<showId>&entity=podcastEpisode&limit=200`. Medium posts that 403
  are often readable through the publication's public RSS feed (`medium.com/feed/<publication>`).
- Write results where the next session finds them (Will's: abernathymagazine `data/wikidata-item-draft.md`),
  graded A (independent + reliable + significant) / B (limited depth) / C (facts only).

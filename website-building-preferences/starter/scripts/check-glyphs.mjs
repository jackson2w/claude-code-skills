// node scripts/check-glyphs.mjs [--strict]  (after eleventy): warn about characters on built pages that the subset fonts
// don't contain (they'd render in a fallback font). Add them to site.fontExtraText and rebuild.
import fs from "node:fs"; import path from "node:path";
import site from "../src/_data/site.js"; import { subsetText } from "./font-ranges.mjs";
const have = new Set(subsetText(site.fontExtraText || "")), missing = new Map();
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(d, e.name)) : e.name.endsWith(".html") ? [path.join(d, e.name)] : []);
const ent = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
for (const f of walk("_site")) {
  const t = fs.readFileSync(f, "utf8").replace(/<(script|style)[\s\S]*?<\/\1>/g, " ").replace(/<[^>]+>/g, " ")
    .replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => e[0] === "#" ? String.fromCodePoint(e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : +e.slice(1)) : (ent[e] ?? m));
  for (const ch of t) if (!have.has(ch) && !/\s/.test(ch)) missing.set(ch, missing.get(ch) || f.replace(/^_site/, ""));
}
if (!missing.size) console.log("check-glyphs: every character on every page is in the font subset");
else { console.log(`check-glyphs: ${missing.size} character(s) not in the font subset (add to site.fontExtraText):`);
  for (const [c, f] of missing) console.log(`  U+${c.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")} ${JSON.stringify(c)} first on ${f}`);
  if (process.argv.includes("--strict")) process.exit(1); }

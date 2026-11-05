// Eleventy 3 config for Will's starter (website-building-preferences/starter). Merge into an existing config rather than replacing it.
import { feedPlugin } from "@11ty/eleventy-plugin-rss";
import rss from "@11ty/eleventy-plugin-rss";
import site from "./src/_data/site.js";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ public: "/" });          // _redirects, favicons, icons/ (_headers is generated)
  eleventyConfig.addPassthroughCopy("src/css");
  eleventyConfig.addPassthroughCopy("src/fonts");
  eleventyConfig.addPassthroughCopy("src/img");
  // "/css/style.css" | fp -> "/css/style.css?v=<content hash>": a changed file gets a new URL, so immutable caching is safe
  eleventyConfig.addFilter("fp", (url) => url + "?v=" + createHash("sha256").update(readFileSync("src" + url)).digest("hex").slice(0, 10));
  eleventyConfig.addPlugin(rss);                                // dateToRfc3339, absoluteUrl, … filters used by head/jsonld/sitemap
  if (site.feed) eleventyConfig.addPlugin(feedPlugin, {         // foundations/feed-discovery + feed-hygiene
    type: "atom", outputPath: site.feed,
    collection: { name: "posts", limit: 20 },
    metadata: { language: site.lang, title: site.name, subtitle: site.description, base: site.url + "/",
                author: { name: site.author.name } },
  });
  return { dir: { input: "src", includes: "_includes", data: "_data", output: "_site" } };
}

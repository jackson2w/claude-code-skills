// Eleventy 3 config for Will's starter (website-building-preferences/starter). Merge into an existing config rather than replacing it.
import { feedPlugin } from "@11ty/eleventy-plugin-rss";
import rss from "@11ty/eleventy-plugin-rss";
import { eleventyImageTransformPlugin } from "@11ty/eleventy-img";
import site from "./src/_data/site.js";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

export default function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy({ public: "/" });          // _redirects, favicons, icons/ (_headers is generated)
  eleventyConfig.addPassthroughCopy("src/css");
  eleventyConfig.addPassthroughCopy("src/fonts");
  eleventyConfig.addPassthroughCopy("src/img/og");                // share images stay plain JPGs at a fixed URL
  // Every <img> in the built HTML becomes a <picture>: AVIF, then WebP, then JPEG, at several widths, with width/height
  // written in (no layout shift) and lazy loading by default. Photos live in src/img/ as originals (never modified).
  // The hero/LCP image sets its own loading="eager" fetchpriority="high" (author attributes win over these defaults)
  // and its own sizes="…". eleventy:ignore skips an image. Generated files are cached in .cache/ between builds.
  eleventyConfig.addPlugin(eleventyImageTransformPlugin, {
    formats: ["avif", "webp", "jpeg"],
    widths: [320, 640, 960, 1600],                                // never upscaled; 320 serves phone thumbnails
    outputDir: "./_site/img/built/", urlPath: "/img/built/",
    sharpOptions: { animated: true },
    htmlOptions: { imgAttributes: { loading: "lazy", decoding: "async", sizes: "(min-width: 60rem) 60rem, 100vw" } },
  });
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

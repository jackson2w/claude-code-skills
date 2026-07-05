// Skeleton build script for a font-preview Artifact. Copy this into a
// scratch directory next to the Fontsource packages, adjust FONTS and the
// HTML/CSS template, then `node build-font-preview.js`.
//
// Why a script and not inline base64 in a Write call: a variable font file
// is tens of KB; base64 inflates that ~33%. Doing the encoding in a script
// keeps that text out of the conversation entirely — only the final file
// path matters, not its content.

const fs = require("fs");
const path = require("path");

const b64 = (p) => fs.readFileSync(path.join(__dirname, p)).toString("base64");

// One entry per font file actually needed. `format` is "woff2-variations"
// for @fontsource-variable/* packages, "woff2" for static @fontsource/*
// packages. `weight` is the family's real min/max (or single value for a
// static font) — check node_modules/<pkg>/files/ and the family's page on
// fontsource.org rather than guessing.
const FONTS = [
  {
    name: "Example Variable",
    file: "node_modules/@fontsource-variable/example/files/example-latin-wght-normal.woff2",
    format: "woff2-variations",
    weight: "300 900",
    style: "normal",
  },
  // { name: "Example Static", file: "node_modules/@fontsource/example-static/files/example-static-latin-400-normal.woff2", format: "woff2", weight: "400", style: "normal" },
];

const fontFaces = FONTS.map(
  (f) => `
@font-face {
  font-family: "${f.name}";
  src: url(data:font/woff2;base64,${b64(f.file)}) format("${f.format}");
  font-weight: ${f.weight};
  font-style: ${f.style};
  font-display: swap;
}`
).join("\n");

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Font preview</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
${fontFaces}

/* TODO: page chrome + comparison sections, reusing the real site's actual
   design tokens (colors, spacing, type scale) and real copy — not generic
   lorem ipsum. See the artifact-design skill for layout/treatment guidance. */
</style>
</head>
<body>
  <!-- TODO: comparison sections -->
</body>
</html>
`;

const outPath = path.join(__dirname, "font-preview.html");
fs.writeFileSync(outPath, html);
console.log("wrote", outPath, html.length, "bytes");

// Favicon set from one letter of the site's own typeface (specification.website foundations/favicons):
// <out>/favicon.svg, favicon.ico (32 px PNG inside ICO), apple-touch-icon.png (180, opaque); <out>/icons/icon-192.png, icon-512.png,
// icon-maskable-512.png (letter inside the 80 % safe zone, full-bleed background).
// NODE_PATH=/usr/lib/node_modules:<dir with opentype.js> node make-icons.cjs <font.ttf|otf> <char> <outdir> <bg> <fg> [shadow]
// Colours are any CSS colour; the SVG keeps them as written, so OKLCH works. shadow = offset copy behind the letter (optional).
const fs = require("node:fs"), path = require("node:path"), opentype = require("opentype.js"), { chromium } = require("playwright");
const [font, ch, out, bg, fg, shadow] = process.argv.slice(2);
const f = opentype.loadSync(font), g = f.charToGlyph(ch), b = g.getBoundingBox();
function svg(size, fill, radius) { // fill = share of the square the letter's larger side takes
  const w = b.x2 - b.x1, h = b.y2 - b.y1, s = (size * fill) / Math.max(w, h);
  const x = (size - w * s) / 2 - b.x1 * s, y = (size + h * s) / 2 + b.y1 * s; // baseline so the glyph box is centred
  const d = (dx, dy) => g.getPath(x + dx, y + dy, f.unitsPerEm * s).toPathData(2);
  const off = size * 0.035;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}">` +
    `<rect width="${size}" height="${size}" rx="${radius}" fill="${bg}"/>` +
    (shadow ? `<path d="${d(off, off * 0.7)}" fill="${shadow}"/>` : "") + `<path d="${d(0, 0)}" fill="${fg}"/></svg>`;
}
fs.mkdirSync(path.join(out, "icons"), { recursive: true }); // favicon.* + apple-touch at the root, PWA icons in /icons/
fs.writeFileSync(path.join(out, "favicon.svg"), svg(64, 0.78, 12));
(async () => {
  const br = await chromium.launch(), p = await br.newPage();
  const png = async (svgText, px) => { await p.setViewportSize({ width: px, height: px });
    await p.setContent(`<html><body style="margin:0">${svgText.replace("<svg ", `<svg width="${px}" height="${px}" `)}</body></html>`);
    return p.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: px, height: px } }); };
  const write = (n, buf) => { fs.writeFileSync(path.join(out, n), buf); console.log(n, buf.length, "bytes"); };
  const ico32 = await png(svg(64, 0.78, 12), 32);
  write("apple-touch-icon.png", await png(svg(180, 0.7, 0), 180));   // iOS rounds it; must be opaque
  write("icons/icon-192.png", await png(svg(192, 0.72, 36), 192));
  write("icons/icon-512.png", await png(svg(512, 0.72, 96), 512));
  write("icons/icon-maskable-512.png", await png(svg(512, 0.56, 0), 512)); // safe zone = central 80 % circle
  const hdr = Buffer.alloc(22); hdr.writeUInt16LE(0, 0); hdr.writeUInt16LE(1, 2); hdr.writeUInt16LE(1, 4);
  hdr.writeUInt8(32, 6); hdr.writeUInt8(32, 7); hdr.writeUInt16LE(1, 10); hdr.writeUInt16LE(32, 12);
  hdr.writeUInt32LE(ico32.length, 14); hdr.writeUInt32LE(22, 18);
  write("favicon.ico", Buffer.concat([hdr, ico32]));
  await br.close();
})();

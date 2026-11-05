// NODE_PATH=/usr/lib/node_modules node og-crop.cjs <src.jpg> <out.jpg> [focalY 0..1] : scale to cover 1200x630, crop around focalY, write JPG for og:image
const { chromium } = require("playwright"); const fs = require("node:fs"); (async () => {
const [src, out, fy = "0.5"] = process.argv.slice(2);
const b = await chromium.launch(); const p = await b.newPage();
const data = fs.readFileSync(src).toString("base64");
const jpg = await p.evaluate(async ({ data, fy }) => {
  const img = new Image(); img.src = "data:image/jpeg;base64," + data; await img.decode();
  const W = 1200, H = 630, s = Math.max(W / img.naturalWidth, H / img.naturalHeight);
  const sw = W / s, sh = H / s, sx = (img.naturalWidth - sw) / 2;
  const sy = Math.min(Math.max(img.naturalHeight * fy - sh / 2, 0), img.naturalHeight - sh);
  const c = document.createElement("canvas"); c.width = W; c.height = H;
  const x = c.getContext("2d"); x.imageSmoothingQuality = "high"; x.drawImage(img, sx, sy, sw, sh, 0, 0, W, H);
  return c.toDataURL("image/jpeg", 0.85); }, { data, fy: Number(fy) });
fs.writeFileSync(out, Buffer.from(jpg.split(",")[1], "base64")); console.log(out, fs.statSync(out).size, "bytes");
await b.close();
})();

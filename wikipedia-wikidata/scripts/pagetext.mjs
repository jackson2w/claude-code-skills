// Render a page in headless Chromium and print its visible text (for JavaScript-built pages).
// Usage: node pagetext.mjs <url> [regex] [chars]
import { chromium } from 'playwright';
const [url, pat = '', n = '600'] = process.argv.slice(2);
const b = await chromium.launch();
const p = await b.newPage({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36', locale: 'en-US' });
let status = 0;
try { const r = await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 }); status = r ? r.status() : 0; await p.waitForTimeout(4000); }
catch (e) { console.log('LOAD ERROR', e.message.split('\n')[0]); }
const t = (await p.evaluate(() => document.body ? document.body.innerText : '')).replace(/\s+/g, ' ');
console.log(`== [${status}] ${await p.title()} | ${t.split(' ').length} words`);
if (pat) { const re = new RegExp(pat, 'gi'); let m, k = 0; while ((m = re.exec(t)) && k < 4) { console.log('  ..', t.slice(Math.max(0, m.index - 150), m.index + +n)); k++; re.lastIndex = m.index + +n; } }
await b.close();

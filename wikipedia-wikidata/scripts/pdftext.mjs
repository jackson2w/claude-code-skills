import { getDocument } from "pdfjs-dist/legacy/build/pdf.mjs";
const doc = await getDocument({ url: process.argv[2], useSystemFonts: true }).promise;
let out = "";
for (let i = 1; i <= doc.numPages; i++) { const c = await (await doc.getPage(i)).getTextContent(); out += `\n--- page ${i} ---\n` + c.items.map(x => x.str + (x.hasEOL ? "\n" : "")).join(""); }
console.log(`pages: ${doc.numPages}`); console.log(out);

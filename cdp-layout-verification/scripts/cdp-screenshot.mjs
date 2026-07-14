// Capture a screenshot of a live page's *current* DOM state via Chrome
// DevTools Protocol — including any live mutations made with cdp-eval.mjs
// (e.g. toggling a class), without reloading the page and losing that state.
// Requires Node 22+ (uses the built-in global WebSocket).
//
// Usage: node cdp-screenshot.mjs <webSocketDebuggerUrl> <output-path.png>

import fs from "node:fs";

const wsUrl = process.argv[2];
const outPath = process.argv[3];

if (!wsUrl || !outPath) {
  console.error("Usage: node cdp-screenshot.mjs <webSocketDebuggerUrl> <output-path.png>");
  process.exit(1);
}

const ws = new WebSocket(wsUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve);
  ws.addEventListener("error", reject);
});

let id = 1;
function send(method, params = {}) {
  const reqId = id++;
  ws.send(JSON.stringify({ id: reqId, method, params }));
  return new Promise((resolve) => {
    const handler = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id === reqId) {
        ws.removeEventListener("message", handler);
        resolve(msg);
      }
    };
    ws.addEventListener("message", handler);
  });
}

await send("Page.enable");
const result = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
fs.writeFileSync(outPath, Buffer.from(result.result.data, "base64"));
console.log("saved to " + outPath);
ws.close();
process.exit(0);

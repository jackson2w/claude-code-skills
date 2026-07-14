// Evaluate a JS expression in a live page via Chrome DevTools Protocol and
// print the result. Requires Node 22+ (uses the built-in global WebSocket).
//
// Usage: node cdp-eval.mjs <webSocketDebuggerUrl> "<js expression>"
//
// Get the webSocketDebuggerUrl by curling the DevTools JSON endpoint of a
// headless Chrome instance launched with --remote-debugging-port=<port>:
//   curl -s http://localhost:<port>/json | python3 -c \
//     "import json,sys; print([t['webSocketDebuggerUrl'] for t in json.load(sys.stdin) if t['type']=='page'][0])"

const wsUrl = process.argv[2];
const expr = process.argv[3];

if (!wsUrl || !expr) {
  console.error("Usage: node cdp-eval.mjs <webSocketDebuggerUrl> \"<js expression>\"");
  process.exit(1);
}

const ws = new WebSocket(wsUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener("open", resolve);
  ws.addEventListener("error", reject);
});

const id = 1;
ws.send(JSON.stringify({ id, method: "Runtime.evaluate", params: { expression: expr, returnByValue: true } }));

const result = await new Promise((resolve) => {
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id === id) resolve(msg);
  });
});

if (result.result?.exceptionDetails) {
  console.error(JSON.stringify(result.result.exceptionDetails, null, 2));
  process.exit(1);
}

console.log(JSON.stringify(result.result?.result?.value ?? result, null, 2));
ws.close();
process.exit(0);

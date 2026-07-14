---
name: cdp-layout-verification
description: This skill should be used when the user asks to "verify this looks right", "check the spacing/alignment/margin", "is this centered", "double check the CSS", "confirm the layout matches", or after any CSS/layout change on a web project where a screenshot alone would only be an eyeball check. It should also be used proactively whenever reporting a CSS fix as "verified" or "confirmed" — a headless screenshot is not sufficient verification for precise spacing, alignment, or color claims; only direct DOM measurement is.
version: 0.1.0
---

# CDP Layout Verification

Verify CSS layout claims (spacing, alignment, color, margins) against the
real, live DOM of a running page, using the Chrome DevTools Protocol (CDP)
directly over a WebSocket — rather than eyeballing a screenshot.

## Why this exists

A headless screenshot can look "close enough" at a glance and lead to a
false "looks good" conclusion, even when the actual computed margin,
alignment, or color is wrong. Two concrete failures this skill prevents:

- A homepage line appeared centered in a screenshot at several widths, but
  was actually offset ~111px left in the real DOM — only caught by measuring
  `getBoundingClientRect()` against the live page, after two rounds of
  screenshot-based "looks fine" were both wrong.
- Three summary lines were meant to have an identical 11px gap between each,
  but a global `p + p { margin-top: ... }` rule silently added 30px to two
  of the three transitions. The screenshot looked plausible; only measuring
  each element's `top`/`bottom` in pixels revealed the inconsistency.

Screenshots are still useful for a final human-readable check, but treat
them as a supplement to measurement, never a replacement for it. When
reporting any layout fix as verified, prefer citing actual measured numbers
over "looks correct in the screenshot."

## Workflow

1. **Serve the built site.** Start (or reuse) a local server for the built
   output — e.g. `npx wrangler pages dev _site --port <port>` for an
   Eleventy/Pages project, or any static server for another stack.

2. **Launch headless Chrome with remote debugging**, sized to the
   breakpoint being verified (mobile vs. desktop matters — a bug can be
   present at one width and absent at another):

   ```bash
   pkill -f "remote-debugging-port=<port>" 2>/dev/null
   ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --headless=new --disable-gpu --remote-debugging-port=<port> \
     --window-size=<W>,<H> "<url>" > /tmp/chrome-debug.log 2>&1 &)
   sleep 3
   ```

   Use a fresh, unused debugging port each time — do not reuse a port from
   an earlier run in the same session without killing the prior process
   first.

3. **Get the page's WebSocket URL:**

   ```bash
   WS=$(curl -s http://localhost:<port>/json | python3 -c "
   import json,sys
   tabs = json.load(sys.stdin)
   for t in tabs:
       if t.get('type') == 'page':
           print(t['webSocketDebuggerUrl'])
           break
   ")
   ```

4. **Measure with `scripts/cdp-eval.mjs`.** Pass a JS expression that
   queries the DOM and returns a plain value (string/number/object — must be
   JSON-serializable, since it goes through `returnByValue`). Prefer
   returning a single formatted string for multiple elements in one call
   over separate calls per element, to keep round-trips low:

   ```bash
   node scripts/cdp-eval.mjs "$WS" "
   (function() {
     function info(sel) {
       var el = document.querySelector(sel);
       if (!el) return sel + ': NOT FOUND';
       var r = el.getBoundingClientRect();
       var cs = getComputedStyle(el);
       return sel + ': left=' + r.left.toFixed(1) + ' top=' + r.top.toFixed(1) +
         ' bottom=' + r.bottom.toFixed(1) + ' color=' + cs.color;
     }
     return [info('.thing-one'), info('.thing-two')].join('\\n');
   })()
   "
   ```

   Compute gaps between elements as `nextEl.top - prevEl.bottom`, not by
   reading a single margin value — margin collapsing between adjacent block
   siblings means the visible gap is not always the sum of both elements'
   declared margins (it is the *max* of the two, unless a rule prevents
   collapsing). If a measured gap doesn't match the sum/expected value of
   the CSS just written, look for another rule contributing to one side
   (see Common Pitfalls below) before assuming the edit didn't apply.

5. **Screenshot the exact current state with `scripts/cdp-screenshot.mjs`**
   when a visual (not just numeric) check is useful — e.g. after confirming
   numbers are right, to also eyeball it, or after mutating the DOM live
   (see below):

   ```bash
   node scripts/cdp-screenshot.mjs "$WS" /path/to/output.png
   ```

6. **Mutate the DOM live to preview a change before committing to it.**
   Because `cdp-eval.mjs` can run arbitrary JS, use it to toggle a class or
   inline style, then screenshot the result — useful for showing a user
   "before vs. after" of a CSS variant without touching the checked-in
   template, or without a full rebuild/reload cycle:

   ```bash
   node scripts/cdp-eval.mjs "$WS" "document.querySelector('.thing').classList.add('is-preview')"
   node scripts/cdp-screenshot.mjs "$WS" /path/to/preview.png
   ```

7. **Clean up.** Always kill the headless Chrome process (and any local dev
   server started just for this) when done:

   ```bash
   pkill -f "remote-debugging-port=<port>" 2>/dev/null
   ```

## Common pitfalls this catches

- **A global sibling-combinator rule** (e.g. `p + p { margin-top: 30px }`)
  silently applies to any two adjacent elements of that tag, including ones
  added inside an unrelated component — the fix is an explicit
  `margin-top: 0` override on the more specific selector, not just adding
  the "correct" margin and assuming it wins.
- **Missing `margin-inline: auto` (or similar) on a new element** inside a
  wider container that relies on a global `max-width` rule for its own
  width — the element gets the width but not the centering, and sits
  flush against one edge instead.
- **A gap that's larger or smaller than expected** almost always means
  another CSS rule is also contributing — check `getComputedStyle` for
  every margin/padding on both elements bordering the gap, not just the one
  just edited.
- **Serving stale CSS.** If measurements don't match what the source CSS
  says they should, diff the actual served/built file (e.g. `_site/**` or
  `dist/**`) against source — a stale build or cached asset can look like a
  CSS bug that isn't one.

## Requirements

- Node 22+ (for the built-in global `WebSocket` used by both scripts —
  earlier versions need a `ws` package polyfill instead).
- A local Chrome/Chromium binary that supports `--headless=new`.
- `curl` and `python3` (or equivalent) for parsing the `/json` debugging
  endpoint response.

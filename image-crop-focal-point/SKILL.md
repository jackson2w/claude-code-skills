---
name: image-crop-focal-point
description: This skill should be used when the user asks to "fix this crop", "the photo is cut off", "set a focal point", "the preview is offset", "recrop this image", "the thumbnail cuts off the head", or any task requiring picking a normalized (x, y) focal point or CSS background-position so a specific subject stays in frame when an image is cropped to a different aspect ratio than its source.
version: 0.1.0
---

# Image Crop Focal Point Estimation

Determine a normalized `(x, y)` focal point (or CSS `background-position`)
so a specific subject stays visible when an image is cropped to a target
aspect ratio different from its source — for a smart-crop pipeline, a CSS
`background-size: cover` box, or any "center of interest" crop parameter.

## Why this exists

Automatic saliency/attention-based cropping (or a naive `center` position)
frequently cuts off heads, faces, or other subjects when the source
photo's aspect ratio differs substantially from the target box — e.g. a
tall 3:4 portrait shot cropped into a wide 3:2 card, or a wide 3:2 group
photo cropped into a 1:1 square thumbnail. Manually picking a focal point
fixes it, but the crop math is easy to get wrong by eyeballing, and doing
it wrong silently ships a bad crop. This skill gives the exact procedure
so it doesn't need to be re-derived (or mis-derived) each time.

## Procedure

1. **View the actual source image file**, not a resized/derivative
   version, at whatever resolution is convenient. Note the tool's reported
   original dimensions and the displayed-to-original scale factor if shown
   (e.g. "original 4284x5712, displayed at 1500x2000, multiply by 2.86") —
   the *fraction* math below doesn't need the multiplier, but it confirms
   which dimension is width vs. height.

2. **Check for EXIF rotation before trusting displayed coordinates.** If
   the image renders sideways or upside-down relative to how it's
   obviously meant to be viewed (e.g. text in the scene runs vertically,
   or the composition is clearly rotated), the file has an EXIF
   orientation tag that image-processing code (e.g. `sharp(buf).rotate()`)
   will apply automatically — but the *tool showing you the image* may or
   may not have applied it. If you must estimate coordinates from a
   sideways render, transform them:
   - 90° CW correction: `(x', y') = (H_raw - y, x)`, new dimensions `(H_raw, W_raw)`.
   - 90° CCW correction: `(x', y') = (y, W_raw - x)`, new dimensions `(H_raw, W_raw)`.
   - 180° correction: `(x', y') = (W_raw - x, H_raw - y)`, same dimensions.
   Always double-check by reasoning about which correction makes the scene
   look upright, not just picking one.

3. **Estimate the subject's bounding box** in the (corrected) image as
   pixel coordinates, then convert to fractions: `x_frac = x / width`,
   `y_frac = y / height`, each in `[0, 1]`. For multiple subjects (e.g. two
   faces), estimate each separately, then average — but sanity-check the
   average actually falls between them, not on top of one.

4. **Compute the crop's visible-fraction along the cropped axis**, since
   this determines whether a candidate focal point actually keeps the
   subject in frame:
   - `source_aspect = source_width / source_height`, `target_aspect = target_width / target_height`.
   - If `source_aspect < target_aspect` (source relatively taller than
     target): cropping happens on the **vertical** axis. Visible height
     fraction = `source_aspect / target_aspect`.
   - If `source_aspect > target_aspect` (source relatively wider than
     target): cropping happens on the **horizontal** axis. Visible width
     fraction = `target_aspect / source_aspect`.
   - If they're equal, no cropping occurs on either axis — any focal point
     works, don't bother setting one.

5. **Choose the focal coordinate on the cropped axis** so the subject's
   bounding box falls inside `[focal - visible_fraction/2, focal +
   visible_fraction/2]`, clamped to `[0, 1]` (a focal point within
   `visible_fraction/2` of an edge gets clamped by the crop implementation
   anyway, so don't overthink exact edge cases — bias inward with a small
   margin instead of hugging `0` or `1`). Leave the other (uncropped) axis
   at `0.5` or a rough visual center — it barely affects anything.

6. **Apply and verify against the real output**, not just the input math:
   - If the pipeline writes actual cropped derivative files (e.g. a
     `sharp().extract()`-based square thumbnail), regenerate and inspect
     the real output image — don't just trust the arithmetic.
   - If the pipeline uses CSS `background-position` at render time (e.g.
     `x_frac*100 + '%'`, `y_frac*100 + '%'`), build a small standalone HTML
     file with the exact same box dimensions/aspect-ratio, image URL, and
     `background-position`/`background-size: cover`, then screenshot it
     (headless Chrome or equivalent) to confirm visually. This is faster
     than a full rebuild/deploy cycle and works even when the image is
     already hosted remotely (point the test file's `<img>`/background URL
     directly at the live/remote asset).

## Worked example

Source photo 5712×4284 (aspect 1.333), target box 3:2 (aspect 1.5).
Since `1.333 < 1.5`, cropping is vertical. Visible height fraction =
`1.333 / 1.5 ≈ 0.889` — so only about 11% of the height is cropped total
(5.5% off each edge at center), meaning even a plain center crop is often
fine here. Contrast with a 3024×4032 portrait (aspect 0.75) into the same
3:2 box: visible height fraction = `0.75 / 1.5 = 0.5` — *half* the image
height is cropped, so a subject anywhere outside the middle 50% (e.g. a
face near the top third) gets cut off by a plain center crop and needs an
explicit focal point, typically `y ≈ 0.2–0.3` for a subject positioned in
the upper part of the frame.

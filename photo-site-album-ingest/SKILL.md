---
name: photo-site-album-ingest
description: This skill should be used when Will asks to "upload photos to the photo site", "import these pictures to photos.jackson2w.com", "make an album", "add these to an album", "put these on the photo site", "set the album cover", "fix the crop on the album page", "the thumbnail cuts off his head", or "place these in <city>" for a photo-site album. Covers the end-to-end ingest for the Eleventy + Cloudflare Pages + R2 site at ~/Claude/photo-site (not Immich): locating dropped files, the wrangler login probe, staging, dry-run and remote ingest, the Dallas/no-GPS location fallback, square-crop review with a contact sheet, focal-point fixes, cover selection, push-to-deploy, and live verification.
version: 0.1.0
---

# Photo-site album ingest

End-to-end procedure for putting a folder of photos onto `photos.jackson2w.com` as an
album. "The photo site" means the repo at `~/Claude/photo-site` — 11ty on Cloudflare Pages,
originals and derivatives in the private R2 bucket `photos-originals`, deploy by `git push`.
It never means Immich. If Will names no service and says "album", default to this.

Two real runs back this skill (2026-09-16 class photos, 2026-11-07 holiday shoot). Both hit
the same two slow spots: a crop that beheaded someone, and a tooling precondition discovered
late. The order below is arranged so the preconditions fail first and the crop review happens
before the push.

## 0. Preconditions, in the order they fail

Run these before touching the photos. Each takes seconds; discovering any of them after the
dry run wastes a turn.

1. **wrangler login.** All R2 writes go through the Mac's wrangler OAuth session. The deploy
   API token in `~/.claude/deploy/credentials.md` has **no** R2 access, so there is no fallback
   when the session has expired, and it does expire (it had on 2026-11-07).
   ```bash
   cd ~/Claude/photo-site && npx wrangler whoami 2>&1 | grep -iE 'logged|error'
   ```
   "Not logged in. Your auth token has expired" means Will must run, in a real terminal:
   ```bash
   cd ~/Claude/photo-site && npx wrangler login
   ```
   Ask for that immediately and do everything else (stage, EXIF, dry run) while waiting.
2. **The repo is clean and current.** `git status --short` and `git log --oneline -1`.
3. **ImageMagick** (`magick`) for the crop review in step 5. `exiftool` is useful for step 2.

## 1. Locate and stage the files

Photos Will drops land as untracked files in whatever repo he has open (both times
`~/homelab`), not on Desktop. `git status --short` there, or `find ~ -mtime -3 -iname '*.jp*g'`.

Stage **copies** in the scratchpad rather than ingesting his folder directly, for two reasons:
the ingest reads a whole folder and writes a `.focal.json` sidecar into it, and dropped files
can arrive with **several filenames glued together with spaces** (one file literally named
`A.jpg B.jpg C.jpg`, seen 2026-11-07). Rename those to the first component when copying:

```bash
S=<scratchpad>/<album-slug>; mkdir -p "$S"
cd <source folder>; for f in *; do case "$f" in *" "*) new="${f%% *}";; *) new="$f";; esac; cp "$f" "$S/$new"; done
```

Leave the originals where they are until the album is verified live; delete only when Will
asks, and compare SHA-256 against the album JSON's `hash` fields before deleting.

## 2. Check EXIF before choosing flags

```bash
exiftool -q -S -DateTimeOriginal -Make -Model -GPSLatitude -FileName <folder>/*
```

- **No `DateTimeOriginal`** (studio prints, scans): pass `--date YYYY-MM` or the album sorts
  last on the home page with no date, which Will reads as "the home page didn't update".
- **No GPS** (most professional shoots): the ingest leaves `gps: null` and no place is shown.
  Will's standing fallback is **Dallas, Texas** unless he says otherwise. Apply it *after* the
  ingest by setting every photo's `gps` in the album JSON — the ingest has no flag for it:
  ```python
  import json; p='src/_data/albums/<slug>.json'; d=json.load(open(p))
  for ph in d['photos']: ph['gps']={'lat':32.7767,'lng':-96.797,'place':'Dallas, Texas, United States'}
  json.dump(d,open(p,'w'),indent=2); open(p,'a').write('\n')
  ```
  `update-focal.mjs` preserves this; a later `ingest.mjs --force` would wipe it, so re-apply
  after any forced re-ingest.

## 3. Dry run, then remote

```bash
cd ~/Claude/photo-site
node scripts/ingest.mjs <slug> <folder> --title "Album Title" [--date YYYY-MM] --dry-run
node scripts/ingest.mjs <slug> <folder> --title "Album Title" [--date YYYY-MM] --remote
```

Slug is kebab-case from the title. `--remote` uploads the original, AVIF/WebP at the width
ladder, one JPEG for link-preview scrapers, and two square thumbnails per photo, then writes
`src/_data/albums/<slug>.json`. Eight 3 MB photos take about two minutes.

**Do not run a local (non-`--remote`) ingest first.** It writes the same JSON, and the remote
run then sees every hash as unchanged and uploads nothing.

Albums are public by default; a password is a separate `cred:<slug>` KV key via
`scripts/set-album-password.mjs`. Ask only if Will mentions privacy.

## 4. Review the square crops before pushing

The album grid is square thumbnails cut by sharp's saliency crop, and it beheads people
regularly: 2 of 3 on the class photos, 1 of 8 plus one tight head on the holiday shoot. Pull
every thumbnail into one sheet and look at it:

```bash
scripts/crop-sheet.sh <slug>        # from this skill's scripts/, run in the repo root
```

It prints the tile order (row-major, four per row) and writes `crop-sheet-<slug>.jpg`; open it
with the Read tool. Also check the home-page cover, which is a 3:2 CSS crop of the cover
photo positioned by the same focal point.

Fix bad tiles with a `.focal.json` in the staged folder, then regenerate only the squares:

```bash
# <folder>/.focal.json — {x,y} is the crop CENTRE in 0..1 after rotation; or a gravity word
{ "IMG_1375.jpeg": { "x": 0.53, "y": 0.47 }, "IMG_0024.jpg": "top" }
node scripts/update-focal.mjs <slug> <folder> --remote
```

Picking coordinates: render the originals with a 10% grid and read the subject's centre off
it — `scripts/grid-sheet.sh out.png a.jpg b.jpg` from this skill, then Read `out.png`. The
crop is a square of side `min(w,h)` centred on `(x·w, y·h)`, clamped to the image, so for a
portrait only `y` matters and for a landscape only `x`. Full method and the CSS-side
equivalent: the `image-crop-focal-point` skill. Rules of thumb from Will's feedback:

- A person "fully centred" wants the crop centre at the midpoint of head and feet, not the
  face.
- "A bit higher in the crop" means move the crop **down** (larger `y`), leaving roughly 10 to
  15 percent headroom above the top head.
- `"top"` beats a numeric `y` when the subject is near the top edge; it leaves the most room.
- Two-person portraits are the ones saliency gets wrong most; check those first.

Re-run `crop-sheet.sh` (or `--photos a,b` for just the changed ones) and look again.
Thumbnail URLs carry a hash of the focal point, so a crop change is a new URL and no cache
busting is needed.

## 5. Cover, build, push

The cover defaults to the first photo by capture date. Change it with `--cover FILE` on the
ingest or by editing `cover` in the album JSON; the home card uses that photo's focal point
as its `background-position`.

```bash
npx @11ty/eleventy 2>&1 | tail -1          # album renders at _site/a/<slug>/index.html
git add src/_data/albums/<slug>.json && git commit -q -m "Add <title> album (<n> photos)" && git push origin main
gh run watch "$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status
```

Album pages are `/a/<slug>/`, photo pages `/a/<slug>/p/<n>/` (1-based, capture-date order);
there is no `/albums/` path. The push is the deploy (about a minute); pushing after a
successful ingest is pre-approved in the repo's `.claude/settings.json`.

## 6. Verify live

```bash
B=https://photos.jackson2w.com
curl -s -o /dev/null -w 'album %{http_code}\n' $B/a/<slug>/
curl -s $B/ | grep -c <slug>                                   # home page lists it
T=$(curl -s $B/a/<slug>/ | grep -oE "/a/<slug>/img/[^\" ]*sq=480[^\" ]*" | head -1 | sed 's/&amp;/\&/g')
curl -s -o /dev/null -w 'thumb %{http_code} %{content_type}\n' -H 'Accept: image/avif,image/webp' "$B$T"
curl -s -o /dev/null -w 'og %{http_code} %{content_type} %{size_download}B\n' -A facebookexternalhit/1.1 -H 'Accept: */*' "$B/a/<slug>/img/<cover>?w=1440"
```

Two traps in that block: the `srcset` attribute holds several URLs with `&amp;`, so decode and
take the first or every probe returns `000`; and image probes need an image `Accept` header to
exercise the AVIF path. The scraper probe should return a JPEG of a few hundred KB — the
full-resolution original means the JPEG derivative is missing (`scripts/backfill-og-jpeg.mjs
<slug> --remote`). A headless-Chrome screenshot of the home page is the fastest check that the
cover crop looks right:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu --hide-scrollbars --window-size=1440,1100 --screenshot=<scratch>/home.png $B/
```

## Reporting

Lead with the album URL. State photo count, where the location came from (EXIF or the Dallas
fallback), which crops were adjusted, and that the originals are still in the drop folder.
Will usually follows up with crop feedback by photo-page URL (`/p/6/`); map `n` back to a
filename with `grep -oE 'img/[^?]+' < page` and go straight to step 4.

## Related

- `project_photo_site_album_ingest` memory: history of both runs and why each rule exists.
- `image-crop-focal-point` skill: the general focal-point method.
- The repo's own `CLAUDE.md` documents the scripts and the derivative layout; this skill is
  the operating procedure around them.

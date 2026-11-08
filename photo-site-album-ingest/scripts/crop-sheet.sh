#!/usr/bin/env bash
# Pull an album's published square thumbnails out of R2 into one contact sheet,
# so every crop can be reviewed in a single image before (or after) pushing.
#
#   crop-sheet.sh <slug> [out.jpg] [--photos a.jpg,b.jpg]
#
# Run from the photo-site repo root (needs the album JSON and a logged-in
# wrangler). Prints the tile order (row-major, 4 per row) so a bad tile can be
# mapped back to its filename. Requires ImageMagick (`magick`).
set -euo pipefail

slug=${1:?usage: crop-sheet.sh <slug> [out.jpg] [--photos a,b]}
shift
out="crop-sheet-${slug}.jpg"
only=""
while [ $# -gt 0 ]; do
  case "$1" in
    --photos) only="$2"; shift 2 ;;
    *) out="$1"; shift ;;
  esac
done

json="src/_data/albums/${slug}.json"
[ -f "$json" ] || { echo "no album JSON at $json (run from the photo-site repo root)" >&2; exit 1; }
command -v magick >/dev/null || { echo "ImageMagick (magick) not installed" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

if [ -n "$only" ]; then
  files=$(tr ',' '\n' <<<"$only")
else
  files=$(python3 -c "import json,sys;[print(p['filename']) for p in json.load(open(sys.argv[1]))['photos']]" "$json")
fi

i=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  i=$((i+1))
  printf '%2d  %s\n' "$i" "$f"
  npx wrangler r2 object get "photos-originals/albums/${slug}/_derived/${f}.sq480.webp" \
    --file "$tmp/$(printf '%03d' "$i").webp" --remote >/dev/null 2>&1 &
done <<<"$files"
wait

# montage prints a harmless font warning when labels are off; ignore it.
magick montage "$tmp"/*.webp -tile 4x -geometry 300x300+6+6 "$out" 2>/dev/null
echo "wrote $out ($i tiles, 4 per row)"

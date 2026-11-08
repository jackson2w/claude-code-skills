#!/usr/bin/env bash
# Render originals with a 10% grid (and magenta centre lines) side by side, for
# picking a normalized focal point (x, y) by eye. Reads any image files.
#
#   grid-sheet.sh out.png photo1.jpg [photo2.jpg ...]
#
# Requires ImageMagick (`magick`). Orientation is applied, so coordinates read
# off the sheet match what sharp(buf).rotate() crops.
set -euo pipefail
out=${1:?usage: grid-sheet.sh out.png photo...}
shift
[ $# -gt 0 ] || { echo "no photos given" >&2; exit 1; }
command -v magick >/dev/null || { echo "ImageMagick (magick) not installed" >&2; exit 1; }

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
n=0
for f in "$@"; do
  n=$((n+1))
  g="$tmp/$(printf '%03d' "$n").png"
  magick "$f" -auto-orient -resize 600x600 "$g"
  W=$(magick identify -format %w "$g"); H=$(magick identify -format %h "$g")
  draw=""
  for i in 1 2 3 4 5 6 7 8 9; do
    draw="$draw line $((W*i/10)),0 $((W*i/10)),$H line 0,$((H*i/10)) $W,$((H*i/10))"
  done
  magick "$g" -stroke '#ff0' -strokewidth 1 -draw "$draw" \
    -stroke '#f0f' -strokewidth 2 -draw "line $((W/2)),0 $((W/2)),$H line 0,$((H/2)) $W,$((H/2))" "$g"
  printf '%2d  %s\n' "$n" "$(basename "$f")"
done
magick montage "$tmp"/*.png -tile "${n}x1" -geometry +10+10 "$out" 2>/dev/null
echo "wrote $out"

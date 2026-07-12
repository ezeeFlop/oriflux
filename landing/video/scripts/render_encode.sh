#!/usr/bin/env bash
# Render FR + EN and encode both under ~12MB, plus poster.
# Usage: render_encode.sh [fr|en|both]   (default both)
set -euo pipefail
ROOT="/Users/cve/GITHUB/spt/oriflux/landing/video"
DEMO="$ROOT/demo"
PUB="/Users/cve/GITHUB/spt/oriflux/landing/public/video"
PY="/Users/cve/GITHUB/spt/oriflux/api/.venv/bin/python"
HF="npx --yes hyperframes@0.7.54"
export HYPERFRAMES_SKIP_SKILLS=1
mkdir -p "$PUB"
WHICH="${1:-both}"

fit_music () {
  # trim the 85s master to the composition total with a soft end fade,
  # so the bed resolves cleanly at the real end of THIS language's cut.
  local total="$1"
  local master="$ROOT/assets/music-bed-master.mp3"
  [ -e "$master" ] || return 0
  local fout; fout=$(echo "$total - 3.5" | bc -l)
  ffmpeg -y -loglevel error -i "$master" -t "$total" \
    -af "afade=t=out:st=${fout}:d=3.5" -ar 44100 -codec:a libmp3lame -q:a 3 \
    "$ROOT/assets/music-bed.mp3"
  cp "$ROOT/assets/music-bed.mp3" "$DEMO/assets/music-bed.mp3"
}

render_lang () {
  local lang="$1"
  echo "== building + rendering $lang =="
  "$PY" "$ROOT/scripts/build_composition.py" "$lang"
  local total; total=$(grep -o 'data-duration="[0-9.]*"' "$DEMO/index.html" | head -1 | grep -o '[0-9.]*')
  echo "  composition total: ${total}s — fitting music bed"
  fit_music "$total"
  ( cd "$DEMO" && $HF render --output "renders/raw-$lang.mp4" )
  local raw="$DEMO/renders/raw-$lang.mp4"
  local fst; fst=$(echo "$total - 0.7" | bc -l)
  # target < 12MB: CRF 28 H.264, AAC 96k. Gentle 0.7s fade to black + audio fade at the end.
  ffmpeg -y -loglevel error -i "$raw" \
    -vf "fade=t=out:st=${fst}:d=0.7" -af "afade=t=out:st=${fst}:d=0.7" \
    -c:v libx264 -profile:v high -pix_fmt yuv420p -crf 28 -preset slow \
    -movflags +faststart -c:a aac -b:a 96k -ar 44100 \
    "$PUB/demo-$lang.mp4"
  local mb; mb=$(du -m "$PUB/demo-$lang.mp4" | cut -f1)
  echo "== demo-$lang.mp4 = ${mb}MB =="
}

if [ "$WHICH" = "both" ] || [ "$WHICH" = "fr" ]; then render_lang fr; fi
if [ "$WHICH" = "both" ] || [ "$WHICH" = "en" ]; then render_lang en; fi

# poster: the brand hero (promise scene logo lockup), ~1280 wide, < 200KB
if [ -f "$PUB/demo-fr.mp4" ]; then
  ffmpeg -y -loglevel error -ss 13 -i "$PUB/demo-fr.mp4" -frames:v 1 \
    -vf "scale=1280:-2" -q:v 3 "$PUB/poster.jpg"
  echo "== poster.jpg = $(du -k "$PUB/poster.jpg" | cut -f1)KB =="
fi

echo "== durations =="
for f in "$PUB"/demo-*.mp4; do
  printf "%s  %ss\n" "$(basename "$f")" \
    "$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f")"
done
# leave FR as the standing composition
"$PY" "$ROOT/scripts/build_composition.py" fr >/dev/null

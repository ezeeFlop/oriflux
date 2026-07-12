#!/usr/bin/env bash
# Bring each language's total runtime into the 75-85s target with a gentle,
# pitch-preserving tempo change. Keeps untouched originals in assets/voice-orig/
# so this is idempotent (always re-derives from the originals).
# Target: ~83s of speech per language -> ~85s total after scene padding.
set -euo pipefail
export LC_ALL=C LANG=C
ROOT="/Users/cve/GITHUB/spt/oriflux/landing/video"
A="$ROOT/assets"; ORIG="$A/voice-orig"; D="$ROOT/demo/assets"
PY="/Users/cve/GITHUB/spt/oriflux/api/.venv/bin/python"
TARGET_VOICE_SUM="${1:-83}"

mkdir -p "$ORIG"
# stash originals once
for f in "$A"/voice-*.mp3; do
  b="$(basename "$f")"
  [ -e "$ORIG/$b" ] || cp "$f" "$ORIG/$b"
done

dur () { ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$1"; }

for lang in fr en; do
  sum=0
  for f in "$ORIG"/voice-"$lang"-*.mp3; do
    sum=$(echo "$sum + $(dur "$f")" | bc -l)
  done
  atempo=$(echo "scale=5; $sum / $TARGET_VOICE_SUM" | bc -l)
  # never slow down; cap acceleration at 1.25 for intelligibility
  cmp=$(echo "$atempo < 1.0" | bc -l); [ "$cmp" = "1" ] && atempo=1.0
  cmp=$(echo "$atempo > 1.25" | bc -l); [ "$cmp" = "1" ] && atempo=1.25
  printf "%s: voice_sum=%.2fs -> atempo=%.4f\n" "$lang" "$sum" "$atempo"
  for f in "$ORIG"/voice-"$lang"-*.mp3; do
    b="$(basename "$f")"
    ffmpeg -y -loglevel error -i "$f" -af "atempo=${atempo}" \
      -ar 44100 -codec:a libmp3lame -q:a 3 "$A/$b"
  done
done

cp "$A"/voice-*.mp3 "$D"/ 2>/dev/null || true
echo "== fitted durations =="
newsum_fr=0; newsum_en=0
for f in "$A"/voice-fr-*.mp3; do newsum_fr=$(echo "$newsum_fr + $(dur "$f")" | bc -l); done
for f in "$A"/voice-en-*.mp3; do newsum_en=$(echo "$newsum_en + $(dur "$f")" | bc -l); done
printf "FR speech total: %.2fs\nEN speech total: %.2fs\n" "$newsum_fr" "$newsum_en"

cd "$ROOT" && "$PY" scripts/build_composition.py fr | tail -1

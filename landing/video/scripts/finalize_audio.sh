#!/usr/bin/env bash
# Run once the voiceover mp3s (voice-{fr,en}-{id}.mp3) + music-bed.mp3 are in
# landing/video/assets/. Normalizes any stray wavs, mirrors to demo/assets, rebuilds FR.
set -euo pipefail
ROOT="/Users/cve/GITHUB/spt/oriflux/landing/video"
A="$ROOT/assets"; D="$ROOT/demo/assets"
PY="/Users/cve/GITHUB/spt/oriflux/api/.venv/bin/python"

shopt -s nullglob
# convert any wavs the team-lead may have dropped instead of mp3
for w in "$A"/voice-*.wav "$A"/music-bed.wav; do
  [ -e "$w" ] || continue
  base="$(basename "${w%.wav}")"
  ffmpeg -y -loglevel error -i "$w" -ac 1 -ar 44100 -codec:a libmp3lame -q:a 3 "$A/$base.mp3"
  echo "converted $(basename "$w") -> $base.mp3"
done

cp "$A"/voice-*.mp3 "$D"/ 2>/dev/null || true
[ -e "$A/music-bed.mp3" ] && cp "$A/music-bed.mp3" "$D"/ || echo "(no music-bed.mp3 yet — voice-only)"
echo "mirrored audio to demo/assets"

echo "== voice count: $(ls "$A"/voice-*.mp3 2>/dev/null | wc -l | tr -d ' ') / 20 =="
echo "== measured durations =="
for f in "$A"/voice-fr-*.mp3 "$A"/voice-en-*.mp3; do
  [ -e "$f" ] || continue
  printf "%s  %ss\n" "$(basename "$f")" \
    "$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$f")"
done

cd "$ROOT" && "$PY" scripts/build_composition.py fr
echo "rebuilt FR composition with real durations"

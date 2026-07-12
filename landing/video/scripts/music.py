#!/usr/bin/env python3
"""Generate the Oriflux demo background music bed on SPT Models (stable-audio-open).

Two calls (47s + 40s, slightly different texture), crossfaded to ~82s, then
volume-normalized low as a bed. Writes assets/music-bed.mp3.
"""
import base64
import os
import subprocess
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
URL = os.environ.get("ORIFLUX_SPT_MODELS_URL", "https://models.sponge-theory.dev/v1").rstrip("/")
if not URL.endswith("/v1"):
    URL = URL + "/v1"
SPEECH = URL + "/audio/speech"
KEY = os.environ.get("ORIFLUX_SPT_MODELS_API_KEY") or os.environ.get("SPT_MODELS_API_KEY", "")
H = {"Authorization": f"Bearer {KEY}"}

PROMPT_A = ("calm modern ambient electronic tech underscore, warm soft analog synth pads, "
            "slow evolving texture, gentle atmospheric pulse, deep low warm bass drone, "
            "no vocals, no drums, no percussion, no lead melody, hopeful confident futuristic, cinematic")
PROMPT_B = ("minimal ambient electronic bed, soft glassy synth pad, sparse bell-like tones, "
            "warm sub bass, slow and spacious, no drums, no percussion, no vocals, "
            "quiet contemplative resolving, cinematic underscore")


def gen(prompt: str, end_s: int, out: Path) -> None:
    r = httpx.post(SPEECH, json={"model": "stable-audio-open-1.0", "input": prompt,
                                 "response_format": "mp3", "audio_end_in_s": end_s},
                   headers=H, timeout=420)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    raw = base64.b64decode(r.json()["audio"]) if "application/json" in ct else r.content
    tmp = out.with_suffix(".src.wav")
    tmp.write_bytes(raw)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                    "-ar", "44100", str(out)], check=True)
    tmp.unlink()


def main() -> int:
    if not KEY:
        print("ERROR: ORIFLUX_SPT_MODELS_API_KEY not set")
        return 2
    a, b = ASSETS / ".music-a.mp3", ASSETS / ".music-b.mp3"
    gen(PROMPT_A, 47, a)
    gen(PROMPT_B, 40, b)
    out = ASSETS / "music-bed.mp3"
    # crossfade A->B over 4s, fade in/out edges
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(a), "-i", str(b),
                    "-filter_complex",
                    "[0:a]afade=t=in:st=0:d=2[a0];"
                    "[a0][1:a]acrossfade=d=4:c1=tri:c2=tri[m];"
                    "[m]afade=t=out:st=78:d=4[out]",
                    "-map", "[out]", str(out)], check=True)
    a.unlink(); b.unlink()
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(out)], capture_output=True, text=True).stdout.strip()
    print(f"music-bed.mp3 duration: {dur}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

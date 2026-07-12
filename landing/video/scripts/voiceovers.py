#!/usr/bin/env python3
"""Generate Oriflux demo voiceovers on SPT Models.

Primary: higgs-audio-v3-tts-4b zero-shot clone — ONE master reference take,
cloned on every segment (FR + EN → same voice). Fallback: omnivoice with the
controlled-vocab instruct, if the higgs cloning probe fails (TorchCodec missing).

Env:
  ORIFLUX_SPT_MODELS_URL   e.g. https://models.sponge-theory.dev/v1  (or /v1 appended)
  ORIFLUX_SPT_MODELS_API_KEY   Bearer key

Reads scripts/script.json, writes assets/voice-{fr,en}-<id>.mp3 + a master ref.
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # landing/video
ASSETS = ROOT / "assets"
SCRIPT = json.loads((HERE / "script.json").read_text())

URL = os.environ.get("ORIFLUX_SPT_MODELS_URL", "https://models.sponge-theory.dev/v1").rstrip("/")
if not URL.endswith("/v1"):
    URL = URL + "/v1"
SPEECH = URL + "/audio/speech"
KEY = os.environ.get("ORIFLUX_SPT_MODELS_API_KEY") or os.environ.get("SPT_MODELS_API_KEY", "")
H = {"Authorization": f"Bearer {KEY}"}

HIGGS = "higgs-audio-v3-tts-4b"
MASTER_TEXT = ("Bonjour, je suis la voix d'Oriflux. Analytics web, produit et API, "
               "sans cookies, sur votre propre infrastructure.")
MASTER_WAV = ASSETS / "voice-master-ref.wav"
MASTER_TXT = ASSETS / "voice-master-ref.txt"

MOOD_TAGS = {
    "excitement": "<|emotion:excitement|><|prosody:expressive_high|>",
    "confidence": "",
    "emphasis": "<|prosody:emphasis|>",
    "contemplation": "<|emotion:contemplation|><|prosody:speed_slow|>",
}


def _post(body: dict) -> bytes:
    r = httpx.post(SPEECH, json=body, headers=H, timeout=420)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    ct = r.headers.get("content-type", "")
    if "application/json" in ct:
        w = r.json()
        b64 = w.get("audio") or w.get("data") or w.get("b64_json")
        if not b64:
            raise RuntimeError(f"no audio field in JSON: {list(w)[:6]}")
        return base64.b64decode(b64)
    return r.content


def _to_mp3(raw: bytes, fname: str) -> None:
    tmp = ASSETS / f".tmp-{fname}.wav"
    tmp.write_bytes(raw)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
         "-ac", "1", "-ar", "44100", "-codec:a", "libmp3lame", "-q:a", "3",
         str(ASSETS / fname)], check=True)
    tmp.unlink()


def make_master() -> bytes:
    if MASTER_WAV.exists():
        return MASTER_WAV.read_bytes()
    print("· generating master reference take …")
    raw = _post({"model": HIGGS, "input": MASTER_TEXT, "response_format": "wav"})
    MASTER_WAV.write_bytes(raw)
    MASTER_TXT.write_text(MASTER_TEXT)
    return raw


def probe_clone(ref_b64: str) -> bool:
    print("· probing higgs cloning …")
    try:
        _post({"model": HIGGS, "input": "Test de clonage.",
               "ref_audio": ref_b64, "ref_text": MASTER_TEXT,
               "response_format": "wav"})
        return True
    except RuntimeError as e:
        print(f"  clone probe failed: {e}")
        return False


def tts_higgs(ref_b64: str, tags: str, text: str, fname: str) -> None:
    raw = _post({"model": HIGGS, "input": f"{tags}{text}",
                 "ref_audio": ref_b64, "ref_text": MASTER_TEXT,
                 "response_format": "wav"})
    _to_mp3(raw, fname)


def instruct_for(lang: str) -> str:
    return "male, middle-aged, low pitch, british accent" if lang == "en" else "male, middle-aged, low pitch"


def tts_omni(lang: str, text: str, fname: str) -> None:
    raw = _post({"model": "omnivoice", "input": text,
                 "instruct": instruct_for(lang), "language": lang,
                 "response_format": "mp3"})
    _to_mp3(raw, fname)


def main() -> int:
    if not KEY:
        print("ERROR: ORIFLUX_SPT_MODELS_API_KEY not set in env", file=sys.stderr)
        return 2
    ASSETS.mkdir(parents=True, exist_ok=True)
    ref = make_master()
    ref_b64 = base64.b64encode(ref).decode()
    use_higgs = probe_clone(ref_b64)
    print(f"· engine: {'higgs zero-shot clone' if use_higgs else 'omnivoice fallback'}")
    for seg in SCRIPT["segments"]:
        tags = MOOD_TAGS.get(seg.get("mood", ""), "")
        for lang in ("fr", "en"):
            fname = f"voice-{lang}-{seg['id']}.mp3"
            print(f"  → {fname}")
            if use_higgs:
                tts_higgs(ref_b64, tags, seg[lang], fname)
            else:
                tts_omni(lang, seg[lang], fname)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

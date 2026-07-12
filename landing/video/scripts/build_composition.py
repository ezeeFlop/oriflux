#!/usr/bin/env python3
"""Generate the Oriflux demo HyperFrames compositions (FR + EN).

Timing flows from the measured voiceover durations. FR -> demo/index.html,
EN -> demo/compositions/main-en.html. Both are standalone roots (no template),
composition-id "main", rendered independently.

Run after voiceovers exist. Falls back to per-segment estimates (dry-run) when
the mp3s are missing, so the structure can be linted before audio.
"""
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO = HERE.parent                       # landing/video
ASSETS = VIDEO / "assets"
DEMO = VIDEO / "demo"
SCRIPT = json.loads((HERE / "script.json").read_text())

# per-segment fallback speech durations (s) if mp3 missing — for dry-run lint
EST = {
    "01-hook": 9.0, "02-promise": 6.0, "03-portfolio": 6.5, "04-web": 7.5,
    "05-aivis": 8.0, "06-api": 8.0, "07-live": 3.6, "08-privacy": 7.0,
    "09-ai-oss": 8.0, "10-cta": 8.0,
}
MIN_SCENE = 4.6          # a scene never shorter than this (lets visuals breathe)
HOLD = 0.55              # visual hold added on top of voice
OVERLAP = 0.5            # scene crossfade window
V_TRACK0 = 8             # first voice track index
MUSIC_TRACK = 18

PAL = dict(
    flame="#d64524", flame_strong="#b8351a",
    flame_soft="rgba(214,69,36,0.08)", flame_tint="rgba(214,69,36,0.14)",
    paper="#f4f5f6", surface="#ffffff", surface2="#fafbfc",
    line="#e3e6ea", line_strong="#d3d8de",
    ink="#17191c", ink_soft="#5f6672", ink_faint="#9aa1ab",
    green="#57c07a",
)

FLAME_PATH = "M4 3h13l-2.5 3.5L17 10H6v11a2 2 0 0 1-2-2V3z"


def dur(mp3: Path) -> float:
    if not mp3.exists():
        return 0.0
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(mp3)],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def flame_svg(size: int, color: str = None) -> str:
    c = color or PAL["flame"]
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">'
            f'<path d="{FLAME_PATH}" fill="{c}"/></svg>')


# ─────────────────────────────────────────────────────────────── localized copy
HUD = {
    "01-hook": ("PROBLÈME", "THE PROBLEM"),
    "02-promise": ("PLATEFORME UNIFIÉE", "UNIFIED PLATFORM"),
    "03-portfolio": ("PORTEFEUILLE", "PORTFOLIO"),
    "04-web": ("WEB · SANS COOKIE", "WEB · COOKIELESS"),
    "05-aivis": ("VISIBILITÉ IA", "AI VISIBILITY"),
    "06-api": ("API ANALYTICS", "API ANALYTICS"),
    "07-live": ("TEMPS RÉEL", "REAL-TIME"),
    "08-privacy": ("VIE PRIVÉE", "PRIVACY"),
    "09-ai-oss": ("IA LOCALE · OPEN SOURCE", "LOCAL AI · OPEN SOURCE"),
}
SCENE_NAME = {
    "01-hook": ("LE CONSTAT", "THE PROBLEM"),
    "02-promise": ("LA PROMESSE", "THE PROMISE"),
    "03-portfolio": ("LE COCKPIT", "THE COCKPIT"),
    "04-web": ("GÉOGRAPHIE", "GEOGRAPHY"),
    "05-aivis": ("AGENTS IA", "AI AGENTS"),
    "06-api": ("VOTRE API", "YOUR API"),
    "07-live": ("EN DIRECT", "LIVE"),
    "08-privacy": ("PAR CONSTRUCTION", "BY CONSTRUCTION"),
    "09-ai-oss": ("LOCAL · OUVERT", "LOCAL · OPEN"),
}
# screencap-scene callouts: (kicker, headline, sub) per lang
CALLOUT = {
    "03-portfolio": {
        "fr": ("PORTEFEUILLE", "Tous vos produits,\nun seul cockpit.", "Visiteurs · Requêtes · Latence · Alertes"),
        "en": ("PORTFOLIO", "Every product,\none cockpit.", "Visitors · Requests · Latency · Alerts"),
    },
    "04-web": {
        "fr": ("WEB · SANS COOKIE", "La géographie\nde votre trafic.", "Sans bannière. Rien à négocier avec un DPO."),
        "en": ("WEB · COOKIELESS", "The geography\nof your traffic.", "No banner. Nothing to negotiate with a DPO."),
    },
    "05-aivis": {
        "fr": ("VISIBILITÉ IA", "Quels agents IA\nvous lisent.", "GPTBot · ClaudeBot · PerplexityBot"),
        "en": ("AI VISIBILITY", "Which AI agents\nread you.", "GPTBot · ClaudeBot · PerplexityBot"),
    },
    "06-api": {
        "fr": ("API ANALYTICS", "Là où le web\nanalytics s'arrête.", "Latence p95 · erreurs · pays d'appel"),
        "en": ("API ANALYTICS", "Where web\nanalytics stops.", "p95 latency · errors · caller country"),
    },
    "07-live": {
        "fr": ("TEMPS RÉEL", "Qui est là,\nmaintenant.", "Actualisé en continu"),
        "en": ("REAL-TIME", "Who's here,\nright now.", "Continuously refreshed"),
    },
}
# which screencap backs each screencap-scene (per lang, filled at build)
SHOT = {
    "03-portfolio": "overview", "04-web": "web-geo", "05-aivis": "web-ai",
    "06-api": "api-geo", "07-live": "live",
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def hl(headline: str) -> str:
    return "<br/>".join(esc(l) for l in headline.split("\n"))


# ───────────────────────────────────────────────────────────── scene renderers
def scene_hud(sid: str, lang: str, i: int) -> str:
    li = 0 if lang == "fr" else 1
    hud = HUD.get(sid, ("", ""))[li]
    name = SCENE_NAME.get(sid, ("", ""))[li]
    n = f"{i:02d}"
    return (
        f'<div class="hud" id="s{i}-hud"><span class="dot"></span>'
        f'<span class="flag">{flame_svg(16)}</span> ORIFLUX <span class="sep">//</span> {esc(hud)}</div>'
        f'<div class="scene-label" id="s{i}-label">SCÈNE {n} · {esc(name)}</div>'
        if lang == "fr" else
        f'<div class="hud" id="s{i}-hud"><span class="dot"></span>'
        f'<span class="flag">{flame_svg(16)}</span> ORIFLUX <span class="sep">//</span> {esc(hud)}</div>'
        f'<div class="scene-label" id="s{i}-label">SCENE {n} · {esc(name)}</div>'
    )


def screencap_scene(sid: str, lang: str, i: int, start: float, dur_s: float, track: int) -> tuple[str, str, str]:
    li = 0 if lang == "fr" else 1
    ap = "assets/"
    shot = f"{ap}screencap-{lang}-{SHOT[sid]}.png"
    kicker, headline, sub = CALLOUT[sid][lang]
    live_extra = ""
    if sid == "07-live":
        live_extra = (f'<div class="live-badge" id="s{i}-livebadge">'
                      f'<span class="live-pulse"></span>'
                      f'{"EN DIRECT" if lang=="fr" else "LIVE"}</div>')
    html = (
        f'<div id="s{i}" class="clip scene scene-shot" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="shot" id="s{i}-shot" style="background-image:url(\'{shot}\')"></div>'
        f'<div class="shot-veil"></div>'
        f'{scene_hud(sid, lang, i)}'
        f'{live_extra}'
        f'<div class="callout" id="s{i}-callout">'
        f'<div class="kicker">{esc(kicker)}</div>'
        f'<div class="headline">{hl(headline)}</div>'
        f'<div class="sub">{esc(sub)}</div>'
        f'</div></div>'
    )
    a = (
        f'tl.from("#s{i}", {{opacity:0, duration:0.5, ease:"power2.out"}}, {start:.3f});\n'
        f'tl.fromTo("#s{i}-shot", {{scale:1.0, xPercent:0, yPercent:0}}, '
        f'{{scale:1.06, yPercent:-2, duration:{dur_s:.3f}, ease:"none"}}, {start:.3f});\n'
        f'tl.from("#s{i}-hud", {{x:-60, opacity:0, duration:0.5, ease:"power3.out"}}, {start+0.3:.3f});\n'
        f'tl.from("#s{i}-label", {{y:-24, opacity:0, duration:0.5, ease:"expo.out"}}, {start+0.45:.3f});\n'
        f'tl.from("#s{i}-callout", {{y:40, opacity:0, filter:"blur(12px)", duration:0.7, ease:"expo.out"}}, {start+0.55:.3f});\n'
    )
    if sid == "07-live":
        a += f'tl.from("#s{i}-livebadge", {{scale:0.7, opacity:0, duration:0.5, ease:"back.out(2)"}}, {start+0.7:.3f});\n'
    return html, "", a


def text_scene_hook(lang, i, start, dur_s, track):
    li = 0 if lang == "fr" else 1
    rows = [("Web analytics", "un outil" if lang == "fr" else "one tool", False),
            ("Product analytics", "un autre" if lang == "fr" else "another", False),
            ("API analytics", "nulle part" if lang == "fr" else "nowhere", True)]
    tail = ("Des bannières. Vos données ailleurs." if lang == "fr"
            else "Cookie banners. Your data elsewhere.")
    rows_html = ""
    for k, (name, where, missing) in enumerate(rows):
        cls = "row missing" if missing else "row"
        rows_html += (f'<div class="{cls}" id="s{i}-row{k}">'
                      f'<span class="rname">{esc(name)}</span>'
                      f'<span class="rwhere">{esc(where)}</span></div>')
    html = (
        f'<div id="s{i}" class="clip scene scene-text" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="text-fill"></div>'
        f'{scene_hud("01-hook", lang, i)}'
        f'<div class="hook-wrap" id="s{i}-wrap"><div class="hook-rows">{rows_html}</div>'
        f'<div class="hook-tail" id="s{i}-tail">{esc(tail)}</div></div></div>'
    )
    a = f'tl.from("#s{i}", {{opacity:0, duration:0.4, ease:"power2.out"}}, {start:.3f});\n'
    for k in range(3):
        a += f'tl.from("#s{i}-row{k}", {{x:-50, opacity:0, duration:0.55, ease:"expo.out"}}, {start+0.3+0.55*k:.3f});\n'
    a += f'tl.from("#s{i}-tail", {{y:26, opacity:0, duration:0.6, ease:"expo.out"}}, {start+2.3:.3f});\n'
    a += (f'tl.from("#s{i}-hud", {{x:-60, opacity:0, duration:0.5, ease:"power3.out"}}, {start+0.2:.3f});\n'
          f'tl.from("#s{i}-label", {{y:-24, opacity:0, duration:0.5, ease:"expo.out"}}, {start+0.4:.3f});\n')
    return html, "", a


def text_scene_promise(lang, i, start, dur_s, track):
    head = ("Web, produit et API analytics." if lang == "fr"
            else "Web, product and API analytics.")
    sub = ("Un seul outil. Sans cookies. Sur votre infrastructure."
           if lang == "fr" else "One tool. Cookieless. On your own infrastructure.")
    html = (
        f'<div id="s{i}" class="clip scene scene-text" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="text-fill"></div>'
        f'{scene_hud("02-promise", lang, i)}'
        f'<div class="promise-wrap">'
        f'<div class="promise-logo" id="s{i}-logo">{flame_svg(74)}<span class="pw">Oriflux</span></div>'
        f'<div class="promise-head" id="s{i}-head">{esc(head)}</div>'
        f'<div class="promise-sub" id="s{i}-sub">{esc(sub)}</div>'
        f'</div></div>'
    )
    a = (
        f'tl.from("#s{i}", {{opacity:0, duration:0.4, ease:"power2.out"}}, {start:.3f});\n'
        f'tl.from("#s{i}-logo", {{y:36, opacity:0, duration:0.7, ease:"expo.out"}}, {start+0.25:.3f});\n'
        f'tl.from("#s{i}-head", {{y:34, opacity:0, filter:"blur(12px)", duration:0.7, ease:"expo.out"}}, {start+0.55:.3f});\n'
        f'tl.from("#s{i}-sub", {{y:24, opacity:0, duration:0.6, ease:"expo.out"}}, {start+0.9:.3f});\n'
        f'tl.from("#s{i}-hud", {{x:-60, opacity:0, duration:0.5, ease:"power3.out"}}, {start+0.2:.3f});\n'
        f'tl.from("#s{i}-label", {{y:-24, opacity:0, duration:0.5, ease:"expo.out"}}, {start+0.4:.3f});\n'
    )
    return html, "", a


def text_scene_privacy(lang, i, start, dur_s, track):
    title = "La confidentialité par construction." if lang == "fr" else "Privacy by construction."
    chips = ([("Sel détruit chaque jour", "hash journalier"),
              ("IP jetée à l'ingestion", "jamais stockée"),
              ("DNT & GPC honorés", "dès l'ingestion")] if lang == "fr"
             else [("Salt destroyed daily", "daily hash"),
                   ("IP discarded at ingestion", "never stored"),
                   ("DNT & GPC honored", "at ingestion")])
    chips_html = ""
    for k, (t, s) in enumerate(chips):
        chips_html += (f'<div class="pchip" id="s{i}-chip{k}">'
                       f'<div class="pchk">{flame_svg(20)}</div>'
                       f'<div class="pctext"><div class="pct">{esc(t)}</div>'
                       f'<div class="pcs">{esc(s)}</div></div></div>')
    html = (
        f'<div id="s{i}" class="clip scene scene-text" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="text-fill"></div>'
        f'{scene_hud("08-privacy", lang, i)}'
        f'<div class="priv-wrap"><div class="priv-title" id="s{i}-title">{esc(title)}</div>'
        f'<div class="priv-chips">{chips_html}</div></div></div>'
    )
    a = (
        f'tl.from("#s{i}", {{opacity:0, duration:0.4, ease:"power2.out"}}, {start:.3f});\n'
        f'tl.from("#s{i}-title", {{y:30, opacity:0, filter:"blur(10px)", duration:0.65, ease:"expo.out"}}, {start+0.3:.3f});\n'
        f'tl.from("#s{i}-hud", {{x:-60, opacity:0, duration:0.5, ease:"power3.out"}}, {start+0.2:.3f});\n'
        f'tl.from("#s{i}-label", {{y:-24, opacity:0, duration:0.5, ease:"expo.out"}}, {start+0.4:.3f});\n'
    )
    for k in range(3):
        a += f'tl.from("#s{i}-chip{k}", {{y:34, opacity:0, duration:0.55, ease:"expo.out"}}, {start+0.7+0.28*k:.3f});\n'
    return html, "", a


def text_scene_aioss(lang, i, start, dur_s, track):
    title = "IA locale. Open source." if lang == "fr" else "Local AI. Open source."
    line1 = ("L'inférence tourne sur vos propres modèles — aucune donnée ne sort."
             if lang == "fr" else "Inference runs on your own models — no data leaves.")
    line2 = ("Et tout le serveur est ouvert." if lang == "fr" else "And the entire server is open.")
    html = (
        f'<div id="s{i}" class="clip scene scene-text" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="text-fill"></div>'
        f'{scene_hud("09-ai-oss", lang, i)}'
        f'<div class="aioss-wrap">'
        f'<div class="aioss-title" id="s{i}-title">{esc(title)}</div>'
        f'<div class="aioss-line" id="s{i}-l1">{esc(line1)}</div>'
        f'<div class="aioss-line soft" id="s{i}-l2">{esc(line2)}</div>'
        f'<div class="agpl-badge" id="s{i}-badge">AGPL-3.0</div>'
        f'</div></div>'
    )
    a = (
        f'tl.from("#s{i}", {{opacity:0, duration:0.4, ease:"power2.out"}}, {start:.3f});\n'
        f'tl.from("#s{i}-title", {{y:30, opacity:0, filter:"blur(10px)", duration:0.65, ease:"expo.out"}}, {start+0.3:.3f});\n'
        f'tl.from("#s{i}-l1", {{y:24, opacity:0, duration:0.6, ease:"expo.out"}}, {start+0.75:.3f});\n'
        f'tl.from("#s{i}-l2", {{y:22, opacity:0, duration:0.6, ease:"expo.out"}}, {start+1.05:.3f});\n'
        f'tl.from("#s{i}-badge", {{scale:0.7, opacity:0, duration:0.55, ease:"back.out(2)"}}, {start+1.4:.3f});\n'
        f'tl.from("#s{i}-hud", {{x:-60, opacity:0, duration:0.5, ease:"power3.out"}}, {start+0.2:.3f});\n'
        f'tl.from("#s{i}-label", {{y:-24, opacity:0, duration:0.5, ease:"expo.out"}}, {start+0.4:.3f});\n'
    )
    return html, "", a


def cta_scene(lang, i, start, dur_s, track):
    tagline = ("Web, produit et API analytics.\nSans cookies, sur votre infrastructure."
               if lang == "fr" else
               "Web, product and API analytics.\nCookieless, on your own infrastructure.")
    p1 = "Essayez le cloud" if lang == "fr" else "Try the cloud"
    p2 = "Déployez-le chez vous" if lang == "fr" else "Self-host it"
    html = (
        f'<div id="s{i}" class="clip scene scene-cta" data-start="{start:.3f}" '
        f'data-duration="{dur_s:.3f}" data-track-index="{track}">'
        f'<div class="text-fill"></div>'
        f'<div class="cta-wrap">'
        f'<div class="cta-logo" id="s{i}-logo">{flame_svg(96)}<span class="cw">Oriflux</span></div>'
        f'<div class="cta-tag" id="s{i}-tag">{hl(tagline)}</div>'
        f'<div class="cta-pills" id="s{i}-pills">'
        f'<span class="pill pill-fill">{esc(p1)}</span>'
        f'<span class="pill pill-line">{esc(p2)}</span></div>'
        f'<div class="cta-agpl" id="s{i}-foot">AGPL-3.0 · Sponge Theory</div>'
        f'</div></div>'
    )
    end = start + dur_s
    a = (
        f'tl.from("#s{i}", {{opacity:0, duration:0.5, ease:"power2.out"}}, {start:.3f});\n'
        f'tl.from("#s{i}-logo", {{scale:0.85, opacity:0, duration:0.8, ease:"expo.out"}}, {start+0.25:.3f});\n'
        f'tl.from("#s{i}-tag", {{y:28, opacity:0, filter:"blur(10px)", duration:0.7, ease:"expo.out"}}, {start+0.7:.3f});\n'
        f'tl.from("#s{i}-pills", {{y:24, opacity:0, duration:0.6, ease:"expo.out"}}, {start+1.1:.3f});\n'
        f'tl.from("#s{i}-foot", {{opacity:0, duration:0.6, ease:"power2.out"}}, {start+1.5:.3f});\n'
    )
    return html, "", a


RENDERERS = {
    "01-hook": text_scene_hook,
    "02-promise": text_scene_promise,
    "08-privacy": text_scene_privacy,
    "09-ai-oss": text_scene_aioss,
    "10-cta": cta_scene,
}


def build(lang: str) -> str:
    segs = SCRIPT["segments"]
    # compute per-scene timing from voice durations
    scenes = []
    t = 0.0
    voices = []
    for i, seg in enumerate(segs, start=1):
        sid = seg["id"]
        vdur = dur(ASSETS / f"voice-{lang}-{sid}.mp3") or EST[sid]
        sdur = max(vdur + HOLD, MIN_SCENE)
        start = t
        scenes.append((i, sid, start, sdur))
        voices.append((i, sid, start, vdur))
        t = start + sdur - OVERLAP
    total = scenes[-1][2] + scenes[-1][3]

    body_scenes, anims = [], []
    for (i, sid, start, sdur) in scenes:
        track = i % 2  # 0/1 alternate
        if sid in RENDERERS:
            h, _, a = RENDERERS[sid](lang, i, start, sdur, track)
        else:
            h, _, a = screencap_scene(sid, lang, i, start, sdur, track)
        body_scenes.append(h)
        anims.append(a)

    # audio clips
    ap = "assets/"
    audio = []
    for k, (i, sid, start, vdur) in enumerate(voices):
        audio.append(
            f'<audio class="clip" id="a{i}" data-start="{start:.3f}" '
            f'data-duration="{vdur:.3f}" data-track-index="{V_TRACK0+k}" '
            f'data-volume="0.95" src="{ap}voice-{lang}-{sid}.mp3"></audio>')
    audio.append(
        f'<audio class="clip" id="music-bed" data-start="0" '
        f'data-duration="{total:.3f}" data-track-index="{MUSIC_TRACK}" '
        f'data-volume="0.12" src="{ap}music-bed.mp3"></audio>')

    font_prefix = "assets/fonts/"
    html = TEMPLATE.format(
        lang=lang, total=f"{total:.3f}",
        css=styles(font_prefix), scenes="\n".join(body_scenes),
        audio="\n".join(audio), anims="".join(anims),
    )
    return html, total


def styles(font_prefix: str) -> str:
    p = PAL
    return f"""
@font-face {{ font-family:"Bricolage"; src:url("{font_prefix}bricolage-grotesque-latin-wght-normal.woff2") format("woff2"); font-weight:200 800; font-display:block; }}
@font-face {{ font-family:"JBMono"; src:url("{font_prefix}jetbrains-mono-latin-wght-normal.woff2") format("woff2"); font-weight:100 800; font-display:block; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:1920px; height:1080px; overflow:hidden; background:{p['paper']}; }}
.scene {{ position:absolute; inset:0; width:1920px; height:1080px; overflow:hidden; color:{p['ink']};
  font-family:"Bricolage", system-ui, sans-serif; }}
.text-fill, .shot-veil {{ position:absolute; inset:0; }}
.text-fill {{ background:
  radial-gradient(1200px 700px at 78% 18%, {p['flame_soft']}, transparent 60%),
  radial-gradient(900px 600px at 12% 88%, rgba(214,69,36,0.05), transparent 60%),
  {p['paper']}; }}
.shot {{ position:absolute; inset:-3%; background-position:center top; background-size:cover;
  background-repeat:no-repeat; will-change:transform; }}
.shot-veil {{ pointer-events:none; background:
  linear-gradient(180deg, rgba(244,245,246,0.35) 0%, rgba(244,245,246,0) 14%, rgba(244,245,246,0) 46%, rgba(244,245,246,0.5) 100%),
  radial-gradient(130% 95% at 50% 42%, transparent 52%, rgba(23,25,28,0.07) 100%); }}

/* HUD + label — pill chips so they stay legible over any screencap region */
.hud {{ position:absolute; top:48px; left:64px; display:inline-flex; align-items:center; gap:10px;
  font-family:"JBMono", monospace; font-size:16px; font-weight:500; letter-spacing:0.15em;
  text-transform:uppercase; color:{p['ink_soft']}; z-index:6;
  padding:11px 20px; border-radius:999px; background:rgba(250,251,252,0.9);
  border:1px solid {p['line']}; box-shadow:0 6px 18px rgba(23,25,28,0.07); }}
.hud .flag {{ display:inline-flex; transform:translateY(1px); }}
.hud .sep {{ color:{p['flame']}; }}
.hud .dot {{ width:9px; height:9px; border-radius:50%; background:{p['flame']};
  box-shadow:0 0 0 0 rgba(214,69,36,0.5); animation:pulse 2.4s ease-out infinite; }}
@keyframes pulse {{ 0%{{box-shadow:0 0 0 0 rgba(214,69,36,0.45);}} 70%{{box-shadow:0 0 0 12px rgba(214,69,36,0);}} 100%{{box-shadow:0 0 0 0 rgba(214,69,36,0);}} }}
.scene-label {{ position:absolute; top:48px; right:64px; font-family:"JBMono", monospace;
  font-size:14px; letter-spacing:0.18em; text-transform:uppercase; color:{p['ink_soft']}; z-index:6;
  padding:11px 20px; border-radius:999px; background:rgba(250,251,252,0.9);
  border:1px solid {p['line']}; box-shadow:0 6px 18px rgba(23,25,28,0.07); }}
/* on text scenes the pills are unnecessary chrome — keep them subtle */
.scene-text .hud, .scene-text .scene-label {{ background:transparent; border-color:transparent; box-shadow:none; }}

/* screencap callout — solid card, legible over any UI region */
.callout {{ position:absolute; left:80px; bottom:80px; max-width:860px; z-index:5;
  background:rgba(250,251,252,0.94); border:1px solid {p['line_strong']}; border-radius:26px;
  padding:42px 48px 46px; box-shadow:0 24px 60px rgba(23,25,28,0.14), 0 2px 6px rgba(23,25,28,0.06); }}
.callout .kicker {{ font-family:"JBMono", monospace; font-size:17px; font-weight:600;
  letter-spacing:0.2em; text-transform:uppercase; color:{p['flame_strong']}; margin-bottom:18px; }}
.callout .headline {{ font-size:66px; line-height:1.0; font-weight:700; letter-spacing:-0.025em; color:{p['ink']}; }}
.callout .sub {{ margin-top:20px; font-size:27px; font-weight:400; color:{p['ink_soft']}; letter-spacing:-0.01em;
  font-family:"JBMono", monospace; }}

/* live badge */
.live-badge {{ position:absolute; top:150px; left:80px; display:inline-flex; align-items:center; gap:11px;
  padding:12px 20px; border-radius:999px; background:{p['surface']}; border:1px solid {p['line_strong']};
  box-shadow:{p['shadow_card'] if 'shadow_card' in p else '0 8px 24px rgba(23,25,28,0.06)'};
  font-family:"JBMono", monospace; font-size:18px; font-weight:600; letter-spacing:0.14em;
  text-transform:uppercase; color:{p['ink']}; z-index:6; }}
.live-pulse {{ width:12px; height:12px; border-radius:50%; background:{p['green']};
  box-shadow:0 0 0 0 rgba(87,192,122,0.55); animation:pulse2 1.6s ease-out infinite; }}
@keyframes pulse2 {{ 0%{{box-shadow:0 0 0 0 rgba(87,192,122,0.5);}} 70%{{box-shadow:0 0 0 14px rgba(87,192,122,0);}} 100%{{box-shadow:0 0 0 0 rgba(87,192,122,0);}} }}

/* hook */
.hook-wrap {{ position:absolute; left:120px; top:50%; transform:translateY(-50%); }}
.hook-rows {{ display:flex; flex-direction:column; gap:8px; }}
.row {{ display:flex; align-items:baseline; gap:28px; }}
.row .rname {{ font-size:104px; line-height:1.02; font-weight:700; letter-spacing:-0.03em; color:{p['ink']}; }}
.row .rwhere {{ font-family:"JBMono", monospace; font-size:26px; letter-spacing:0.02em; color:{p['ink_faint']}; }}
.row.missing .rname {{ color:{p['ink_faint']}; text-decoration:line-through; text-decoration-color:{p['flame']}; text-decoration-thickness:6px; }}
.row.missing .rwhere {{ color:{p['flame_strong']}; font-weight:600; }}
.hook-tail {{ margin-top:44px; font-size:40px; font-weight:500; color:{p['ink_soft']}; letter-spacing:-0.01em; }}

/* promise */
.promise-wrap {{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:center;
  align-items:center; text-align:center; padding:0 160px; }}
.promise-logo {{ display:flex; align-items:center; gap:18px; margin-bottom:40px; }}
.promise-logo .pw {{ font-size:64px; font-weight:600; letter-spacing:-0.02em; color:{p['ink']}; }}
.promise-head {{ font-size:100px; line-height:1.0; font-weight:700; letter-spacing:-0.03em; color:{p['ink']}; max-width:1440px; }}
.promise-sub {{ margin-top:34px; font-size:40px; font-weight:400; color:{p['ink_soft']}; letter-spacing:-0.01em; }}

/* privacy */
.priv-wrap {{ position:absolute; left:120px; top:50%; transform:translateY(-50%); right:120px; }}
.priv-title {{ font-size:82px; line-height:1.02; font-weight:700; letter-spacing:-0.03em; color:{p['ink']}; max-width:1400px; margin-bottom:66px; }}
.priv-chips {{ display:flex; gap:28px; }}
.pchip {{ flex:1; display:flex; gap:18px; align-items:flex-start; padding:34px 32px; border-radius:22px;
  background:{p['surface']}; border:1px solid {p['line']}; box-shadow:0 10px 30px rgba(23,25,28,0.05); }}
.pchk {{ flex:none; width:48px; height:48px; border-radius:12px; background:{p['flame_soft']};
  display:flex; align-items:center; justify-content:center; }}
.pctext .pct {{ font-size:32px; font-weight:600; letter-spacing:-0.015em; color:{p['ink']}; line-height:1.1; }}
.pctext .pcs {{ margin-top:8px; font-family:"JBMono", monospace; font-size:19px; letter-spacing:0.02em; color:{p['ink_faint']}; }}

/* ai + oss */
.aioss-wrap {{ position:absolute; left:120px; top:50%; transform:translateY(-50%); right:120px; }}
.aioss-title {{ font-size:104px; line-height:1.0; font-weight:700; letter-spacing:-0.03em; color:{p['ink']}; margin-bottom:40px; }}
.aioss-line {{ font-size:44px; font-weight:400; color:{p['ink_soft']}; letter-spacing:-0.01em; max-width:1400px; line-height:1.2; }}
.aioss-line.soft {{ margin-top:14px; color:{p['ink_faint']}; }}
.agpl-badge {{ display:inline-block; margin-top:44px; padding:16px 30px; border-radius:14px;
  background:{p['flame']}; color:#fff; font-family:"JBMono", monospace; font-size:30px; font-weight:700; letter-spacing:0.04em; }}

/* cta */
.scene-cta {{ }}
.cta-wrap {{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:center;
  align-items:center; text-align:center; padding:0 140px; }}
.cta-logo {{ display:flex; align-items:center; gap:22px; margin-bottom:40px; }}
.cta-logo .cw {{ font-size:96px; font-weight:700; letter-spacing:-0.03em; color:{p['ink']}; }}
.cta-tag {{ font-size:52px; line-height:1.14; font-weight:500; color:{p['ink_soft']}; letter-spacing:-0.015em; max-width:1400px; }}
.cta-pills {{ display:flex; gap:24px; margin-top:52px; }}
.pill {{ padding:22px 46px; border-radius:999px; font-size:34px; font-weight:600; letter-spacing:-0.01em; }}
.pill-fill {{ background:{p['flame']}; color:#fff; }}
.pill-line {{ background:transparent; color:{p['ink']}; border:2px solid {p['line_strong']}; }}
.cta-agpl {{ margin-top:52px; font-family:"JBMono", monospace; font-size:22px; letter-spacing:0.12em;
  text-transform:uppercase; color:{p['ink_faint']}; }}
"""


TEMPLATE = """<!doctype html>
<html lang="{lang}" data-resolution="landscape">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=1920, height=1080" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{css}</style>
</head>
<body>
<div id="root" data-composition-id="main" data-width="1920" data-height="1080" data-start="0" data-duration="{total}">
{scenes}
{audio}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{anims}
window.__timelines["main"] = tl;
</script>
</body>
</html>
"""

# shadow_card token for f-string convenience
PAL["shadow_card"] = "0 8px 24px rgba(23,25,28,0.06)"


def main() -> int:
    import sys
    lang = sys.argv[1] if len(sys.argv) > 1 else "fr"
    if lang not in ("fr", "en"):
        print(f"usage: build_composition.py [fr|en]"); return 2
    html, total = build(lang)
    (DEMO / "index.html").write_text(html)   # single discoverable root
    print(f"{lang.upper()} total {total:.2f}s -> demo/index.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

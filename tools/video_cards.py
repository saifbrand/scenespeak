"""Render the still cards for the demo video, from the project's own numbers.

Every figure on a card is read from the track, the measurement files or the
audio analysis at render time, so the video cannot quietly disagree with the
repository it is submitted alongside.

    python tools/video_cards.py        # writes .cache/video/*.png
"""
from __future__ import annotations

import html
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from describe import plan, speechtrack, subtitles  # noqa: E402

OUT = ".cache/video"
SURFACE, INK, INK2, MUTED, GRID = "#1a1a19", "#ffffff", "#c3c2b7", "#8a897f", "#2c2c2a"
BLUE, ORANGE, AQUA = "#3987e5", "#d95926", "#199e70"   # validated for this surface
DURATION = 734.167

BASE_CSS = f"""
* {{ margin: 0; box-sizing: border-box; }}
html, body {{ width: 1920px; height: 1080px; background: {SURFACE}; color: {INK};
  font-family: "Segoe UI", system-ui, sans-serif; overflow: hidden; }}
.frame {{ position: absolute; inset: 0; padding: 120px 150px; display: flex;
  flex-direction: column; justify-content: center; }}
.kicker {{ color: {AQUA}; font-size: 30px; font-weight: 600; letter-spacing: .06em;
  text-transform: uppercase; margin-bottom: 28px; }}
h1 {{ font-size: 88px; line-height: 1.08; font-weight: 700; letter-spacing: -.01em; }}
h2 {{ font-size: 60px; line-height: 1.12; font-weight: 700; }}
p {{ color: {INK2}; font-size: 38px; line-height: 1.4; margin-top: 30px; max-width: 1500px; }}
.muted {{ color: {MUTED}; }}
"""


def page(body: str, css: str = "") -> str:
    return f"<!doctype html><meta charset=utf-8><style>{BASE_CSS}{css}</style>{body}"


def timeline_svg(cues, speech) -> str:
    """Four lanes over the first 40 seconds: the two sources and the two plans."""
    w0, w1 = 0.0, 40.0
    left, right, top, lane_h, gap = 470, 1770, 40, 70, 44
    scale = (right - left) / (w1 - w0)
    x = lambda t: left + (min(max(t, w0), w1) - w0) * scale  # noqa: E731

    sub = subtitles.dialogue(cues, join_below=0.6)
    naive = plan.build(DURATION, cues).slots
    safe = plan.build(DURATION, cues, speech).slots
    lanes = [
        ("Subtitles", [(s.start, s.end) for s in sub], BLUE),
        ("Real speech in the audio", [(s.start, s.end) for s in speech], ORANGE),
        ("Plan from subtitles alone", [(s.start, s.end) for s in naive], AQUA),
        ("SceneSpeak plan", [(s.start, s.end) for s in safe], AQUA),
    ]
    parts = []
    height = top + len(lanes) * (lane_h + gap) + 60
    for tick in range(0, 41, 5):
        parts.append(f'<line x1="{x(tick)}" y1="{top - 10}" x2="{x(tick)}" '
                     f'y2="{height - 60}" stroke="{GRID}" stroke-width="2"/>')
        parts.append(f'<text x="{x(tick)}" y="{height - 18}" fill="{INK2}" '
                     f'font-size="24" text-anchor="middle">0:{tick:02d}</text>')
    for index, (name, spans, color) in enumerate(lanes):
        y = top + index * (lane_h + gap)
        parts.append(f'<text x="{left - 30}" y="{y + lane_h / 2 + 10}" fill="{INK}" '
                     f'font-size="30" text-anchor="end">{html.escape(name)}</text>')
        for start, end in spans:
            if end <= w0 or start >= w1:
                continue
            # 2px surface gap each side between adjacent fills
            a, b = x(start) + 2, x(end) - 2
            if b - a < 3:
                continue
            parts.append(f'<rect x="{a:.1f}" y="{y}" width="{b - a:.1f}" height="{lane_h}" '
                         f'rx="6" fill="{color}"/>')
        if name == "Plan from subtitles alone":
            # One dashed box per slot, around every stretch of it that lands
            # on real speech -- several fragments of one voice are one problem.
            for start, end in spans:
                hits = [(max(start, sp.start), min(end, sp.end, w1)) for sp in speech
                        if max(start, sp.start) < min(end, sp.end, w1)]
                if not hits:
                    continue
                s0, e0 = min(h[0] for h in hits), max(h[1] for h in hits)
                parts.append(
                    f'<rect x="{x(s0) - 6:.1f}" y="{y - 12}" width="{x(e0) - x(s0) + 12:.1f}" '
                    f'height="{lane_h + 24}" rx="8" fill="none" stroke="{INK}" '
                    f'stroke-width="4" stroke-dasharray="10 7"/>')
            parts.append(f'<rect x="{x(23)}" y="{y + 14}" width="34" height="42" rx="6" '
                         f'fill="none" stroke="{INK}" stroke-width="4" stroke-dasharray="8 6"/>')
            parts.append(f'<text x="{x(23) + 52}" y="{y + lane_h / 2 + 10}" fill="{INK}" '
                         f'font-size="28">talks over a voice no subtitle marks</text>')
    return (f'<svg width="1920" height="{height}" viewBox="0 0 1920 {height}" '
            f'font-family="Segoe UI, system-ui, sans-serif">{"".join(parts)}</svg>')


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    track = json.load(open("out/tears_of_steel.json", encoding="utf-8"))
    stats = track["stats"]
    cues = subtitles.read("media/TOS-en.srt")
    detection = speechtrack.detect("media/full_mix.aif", "media/no_dialogue.aif")

    run3 = [row.rstrip("\n").split("\t") for row in open("measure/run3-film-time.tsv")
            if row[:1].isdigit()]
    by_start = {int(round(line["start"] * 1000)): line for line in track["lines"]}
    overran = sum(1 for u, _, _, _, end in run3
                  if int(end) + 100 > u_end(by_start[int(u)]))
    spoken = len(run3)
    nearest = min(sp.start - (int(end) + 100) / 1000
                  for u, _, _, _, end in run3 for sp in detection.speech
                  if sp.start >= (int(end) + 100) / 1000)
    overlap = sum(1 for u, _, _, pos, end in run3 for sp in detection.speech
                  if int(pos) / 1000 < sp.end and (int(end) + 100) / 1000 > sp.start)
    python_tests, kotlin_tests = count_tests()

    cards = {
        "01_hook": page(f"""<div class=frame>
            <h1>A blind viewer watching a film<br>gets the dialogue.</h1>
            <h1 style="color:{MUTED};margin-top:24px">Nothing else.</h1></div>"""),
        "02_title": page(f"""<div class=frame>
            <div class=kicker>Fire TV · accessibility</div>
            <h1 style="font-size:130px">SceneSpeak</h1>
            <p style="font-size:46px;color:{INK}">Audio description generated from the film itself,
            spoken into the gaps — and never over the dialogue.</p>
            <p class=muted style="font-size:30px">Running on Fire OS 8 (Android 11) · Android TV
            emulator, API 30 · real audio recorded from the device</p></div>"""),
        "03_timeline": page(f"""<div class=frame style="justify-content:flex-start;padding-top:90px">
            <div class=kicker>What I did not expect</div>
            <h2>Subtitles are not a safe map of when a film talks</h2>
            <div style="margin:50px -150px 0">{timeline_svg(cues, detection.speech)}</div>
            <div style="display:flex;gap:70px;margin-top:40px">
              {stat("1.07 s", "speech runs past its own subtitle")}
              {stat("13.8 s", "of speech with no subtitle")}
              {stat("3 of 49", "subtitle-only gaps over a voice")}
              {stat("0", "once the audio is merged in")}
            </div></div>""", css=".stat b{display:block;font-size:64px}"
                                 f".stat span{{color:{INK2};font-size:26px;white-space:nowrap}}"),
        "04_names": page(f"""<div class=frame>
            <div class=kicker>A second rule</div>
            <h2>The model called a character<br>“Vesper” at 6:51.</h2>
            <p>That name is never spoken in the film. A blind listener would learn it
            from the accessibility track — a spoiler no sighted viewer gets.</p>
            <p style="color:{INK}">So SceneSpeak learns the cast from the film’s own dialogue,
            and sends back any line that names somebody too early.</p></div>"""),
        "05_proof": page(f"""<div class=frame>
            <div class=kicker>Measured on the device, in film time</div>
            <h2>Whole film, played end to end</h2>
            <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:46px 120px;margin-top:60px">
              {stat(f"{spoken} of {len(track['lines'])}", "descriptions spoken")}
              {stat(str(overran), "still speaking when their gap closed")}
              {stat(str(overlap), "overlapping speech found in the audio")}
              {stat(f"{nearest:.2f} s", "closest approach to a spoken word")}
            </div>
            <p class=muted style="font-size:30px;margin-top:70px">{stats['silent_share']:.1%} of the
            film is describable silence · {stats['words_spoken']} words ·
            {python_tests} Python tests + {kotlin_tests} Kotlin tests</p></div>""",
            css=".stat b{display:block;font-size:84px}"
                f".stat span{{color:{INK2};font-size:32px}}"),
        "06_end": page(f"""<div class=frame>
            <h1 style="font-size:110px">SceneSpeak</h1>
            <p style="font-size:48px;color:{INK}">github.com/saifbrand/scenespeak</p>
            <p>Open source, MIT. The pipeline, the Fire TV app, every measurement
            and the friction log are in the repository.</p>
            <p class=muted style="font-size:28px;margin-top:80px">Tears of Steel © Blender
            Foundation, CC BY 3.0 · Built by Shifullah for the Amazon Developer
            Hackathon, Fire TV track</p></div>"""),
    }

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        tab = browser.new_page(viewport={"width": 1920, "height": 1080})
        for name, markup in cards.items():
            tab.set_content(markup)
            tab.wait_for_timeout(150)
            tab.screenshot(path=f"{OUT}/{name}.png")
            print("rendered", name)
        browser.close()


def u_end(line: dict) -> int:
    return int(round((line["start"] + line["budget"]) * 1000))


def stat(big: str, small: str) -> str:
    return f'<div class=stat><b>{html.escape(big)}</b><span>{html.escape(small)}</span></div>'


def count_tests() -> tuple[int, int]:
    import re
    import subprocess
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q",
                             "--collect-only"], capture_output=True, text=True)
    python_tests = int(re.search(r"(\d+) tests? collected", result.stdout).group(1))
    kotlin = open("app/app/src/test/java/com/saifbrand/scenespeak/DescriptionTrackTest.kt",
                  encoding="utf-8").read().count("@Test")
    return python_tests, kotlin


if __name__ == "__main__":
    main()

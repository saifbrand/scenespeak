"""Fit the timing model to what the television actually said.

The pipeline has to know how long a line will take to speak before it
commits it to the track, and it cannot know that from first principles: it
depends on the engine, the voice, and whatever speech rate the viewer has
set. So the app writes down the real duration of every line it speaks, and
this reads that back and fits the constants in `describe/speech.py` to it.

    adb shell run-as com.saifbrand.scenespeak cat files/spoken.tsv > spoken.tsv
    python tools/calibrate.py spoken.tsv out/tears_of_steel.json

It also reports the thing that actually matters, which is not the fit: how
many lines took longer than the silence they were given. That number has to
be zero, and it is measured here rather than asserted.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from describe import speech  # noqa: E402


def read_measurements(path: str) -> dict[int, tuple[str, int]]:
    """Map each line's start time in milliseconds to what it did."""
    spoken: dict[int, tuple[str, int]] = {}
    ENDED.clear()
    with open(path, encoding="utf-8") as handle:
        for number, row in enumerate(handle):
            parts = row.rstrip("\n").split("\t")
            if number == 0 and parts[0] == "utterance":
                continue
            if len(parts) < 3:
                continue
            try:
                spoken[int(parts[0])] = (parts[1], int(parts[2]))
                if len(parts) >= 5:
                    ENDED[int(parts[0])] = int(parts[4])
            except ValueError:
                continue
    return spoken


# Where the film was when each line stopped, in milliseconds of film time,
# for recordings made by a player new enough to write it down.
ENDED: dict[int, int] = {}

# The player reads the film's position every 100 ms, so a recorded end
# position can be up to one tick behind the truth. It is added before
# judging, never subtracted.
TICK_MS = 100


def features(text: str) -> tuple[float, float, float]:
    """The three things the duration model is built from."""
    import re
    words = speech.WORDS.findall(text)
    beats = float(sum(speech.syllables(word) for word in words))
    pauses = float(len(re.findall(r"[,;:.](?:\s|$)", text)))
    return 1.0, beats, pauses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", help="spoken.tsv pulled from the device")
    parser.add_argument("track", help="the description track that was played")
    parser.add_argument("--out", default="calibration.json")
    parser.add_argument("--device", default="Fire TV (Android 11) / com.google.android.tts",
                        help="what was measured, recorded in the file")
    parser.add_argument("--safety", type=float, default=1.08)
    args = parser.parse_args(argv)

    with open(args.track, encoding="utf-8") as handle:
        track = json.load(handle)
    spoken = read_measurements(args.measurements)

    rows, seconds, overruns, unfinished = [], [], [], []
    for line in track["lines"]:
        key = int(round(line["start"] * 1000))
        if key not in spoken:
            continue
        outcome, measured_ms = spoken[key]
        if outcome != "done":
            # A line that was cut off tells us nothing about how long it
            # would have taken, only that the hard stop worked.
            unfinished.append((line, outcome))
            continue
        rows.append(features(line["text"]))
        seconds.append(measured_ms / 1000)
        if key in ENDED:
            # The real test of the rule: was the film still inside this
            # line's slot when the voice stopped? Film time, not wall time --
            # on a loaded device the two drift apart by seconds.
            slot_end = key + int(round(line["budget"] * 1000))
            if ENDED[key] + TICK_MS > slot_end:
                overruns.append((line, (ENDED[key] + TICK_MS - key) / 1000))
        elif measured_ms / 1000 > line["budget"]:
            overruns.append((line, measured_ms / 1000))

    if len(rows) < 5:
        print(f"Only {len(rows)} finished lines were measured; not enough to fit.")
        return 1

    design = np.array(rows)
    measured = np.array(seconds)
    fitted, *_ = np.linalg.lstsq(design, measured, rcond=None)
    overhead, per_syllable, per_pause = (float(value) for value in fitted)

    before = np.array([speech.duration(line["text"])
                       for line in track["lines"]
                       if int(round(line["start"] * 1000)) in spoken
                       and spoken[int(round(line["start"] * 1000))][0] == "done"])
    after = design @ fitted

    calibration = speech.Calibration(
        overhead=round(overhead, 4),
        per_syllable=round(per_syllable, 4),
        per_pause=round(max(0.0, per_pause), 4),
        safety=args.safety,
        source=args.device,
    )
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(calibration.__dict__, handle, indent=2)
        handle.write("\n")

    print(f"{len(rows)} lines measured on {args.device}")
    print(f"  measured speech: {measured.sum():.1f}s total, "
          f"{measured.mean():.2f}s per line")
    print(f"  old estimate off by {np.abs(before - measured).mean():.2f}s per line")
    print(f"  fitted estimate off by {np.abs(after - measured).mean():.2f}s per line")
    print(f"  fitted: overhead={overhead:.3f}s per_syllable={per_syllable:.4f}s "
          f"per_pause={per_pause:.3f}s -> {args.out}")

    if unfinished:
        print(f"\n{len(unfinished)} line(s) did not finish naturally:")
        for line, outcome in unfinished[:5]:
            print(f"  {line['start']:8.2f}s {outcome}: {line['text'][:60]}")

    unspoken = [line for line in track["lines"]
                if int(round(line["start"] * 1000)) not in spoken]
    print(f"\nlines the player never started: {len(unspoken)}")
    for line in unspoken[:10]:
        print(f"  {line['start']:8.2f}s budget {line['budget']:.2f}s: {line['text'][:60]}")

    judged = "film time" if ENDED else "wall-clock time (recording predates end positions)"
    print(f"\nlines that overran their silence, judged in {judged}: {len(overruns)}")
    for line, took in overruns[:10]:
        print(f"  {line['start']:8.2f}s took {took:.2f}s of {line['budget']:.2f}s: "
              f"{line['text'][:60]}")
    return 1 if overruns else 0


if __name__ == "__main__":
    sys.exit(main())

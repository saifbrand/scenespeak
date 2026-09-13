"""Command line for the description pipeline.

    python -m describe.cli --writer stub          # no key, no network
    python -m describe.cli --writer gemini        # writes the real track
"""
from __future__ import annotations

import argparse
import json
import sys

from dataclasses import replace

from describe import gaps, speech, vision
from describe.build import Sources, run

FILM = Sources(
    name="Tears of Steel",
    video="media/tears_of_steel_720p.mov",
    subtitles="media/TOS-en.srt",
    full_mix="media/full_mix.aif",
    no_dialogue="media/no_dialogue.aif",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--writer", choices=("stub", "gemini"), default="stub")
    parser.add_argument("--model", default="", help="override the model name")
    parser.add_argument("--out", default="out/tears_of_steel.json")
    parser.add_argument("--vtt", default="", help="also write WebVTT here")
    parser.add_argument("--limit", type=int, default=0,
                        help="only build the first N slots, for a quick look")
    parser.add_argument("--frames", type=int, default=3,
                        help="frames sampled per slot")
    parser.add_argument("--language", default="",
                        help="BCP 47 tag to write the description in, e.g. "
                             "bn. Needs its own calibration and a voice on "
                             "the device; see README.")
    parser.add_argument("--no-audio", action="store_true",
                        help="plan from subtitles alone, ignoring the stems")
    args = parser.parse_args(argv)

    calibration = speech.Calibration.load()
    if args.language:
        # A language change invalidates the timing constants, and silently
        # reusing English ones would size every Bengali line against English
        # syllables. Better to say so and fall back to the defaults, which
        # the device then corrects by measurement.
        if args.language != calibration.language:
            print(f"calibration is for '{calibration.language}'; using "
                  f"defaults for '{args.language}' until it is measured on "
                  f"the device (tools/calibrate.py)")
            calibration = speech.Calibration(language=args.language)
        else:
            calibration = replace(calibration, language=args.language)
    sources = FILM
    if args.no_audio:
        sources = Sources(FILM.name, FILM.video, FILM.subtitles)

    if args.writer == "gemini":
        writer = vision.GeminiWriter(model=args.model, calibration=calibration)
    else:
        writer = vision.StubWriter()

    track = run(sources, writer, policy=gaps.Policy(), calibration=calibration,
                frames_per_slot=args.frames, limit=args.limit)
    track.save(args.out)
    if args.vtt:
        with open(args.vtt, "w", encoding="utf-8") as handle:
            handle.write(track.to_vtt())

    print(json.dumps(track.stats, indent=2))
    print(f"\n{len(track.lines)} lines -> {args.out}")
    collisions = track.stats.get("collisions_with_measured_speech")
    if collisions:
        print(f"FAILED: {collisions} description(s) overlap measured speech")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run the whole pipeline for one film and produce its description track.

The order matters and is the argument of the project: decide where speech
is, derive the openings from that, and only then write words -- each one
sized to the opening it was written for and checked against it afterwards.
Writing first and hoping it fits is how audio description goes wrong.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from describe import (frames, gaps, names, plan, speech, speechtrack,
                      subtitles, vision)
from describe.subtitles import Cue
from describe.track import Line, Track


@dataclass
class Sources:
    """The files one film is built from."""

    name: str
    video: str
    subtitles: str
    full_mix: str = ""
    no_dialogue: str = ""
    """The music-and-effects stem, when the film ships one. Without it the
    plan is made from subtitles alone, which is weaker and says so."""


class Cache:
    """Remembers what the model already wrote for a slot.

    A run is dozens of requests against a metered endpoint. Re-running after
    a crash, a tweak to the margins, or a change to the player should not
    spend the whole quota again, and it should not silently produce
    *different* words either -- a demo you cannot reproduce is not evidence.
    """

    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as handle:
                self.entries: dict = json.load(handle)
        except (OSError, json.JSONDecodeError):
            self.entries = {}

    @staticmethod
    def key(writer: str, start: float, budget: float, attempt: int = 0) -> str:
        return f"{writer}|{start:.3f}|{budget:.3f}" + (f"|{attempt}" if attempt else "")

    def get(self, key: str) -> str | None:
        return self.entries.get(key)

    def put(self, key: str, text: str) -> None:
        self.entries[key] = text
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.entries, handle, indent=1, ensure_ascii=False)


def nearby(cues: list[Cue], slot: gaps.Slot) -> tuple[list[str], list[str]]:
    """The dialogue on either side of a slot, for context."""
    before = [cue.text for cue in cues if cue.end <= slot.start][-3:]
    after = [cue.text for cue in cues if cue.start >= slot.end][:2]
    return before, after


def run(sources: Sources, writer, out_dir: str = "out",
        policy: gaps.Policy = gaps.Policy(),
        calibration: speech.Calibration = speech.Calibration(),
        frames_per_slot: int = 3, limit: int = 0,
        work: str = ".cache") -> Track:
    """Build the description track, and report on itself while doing it."""
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    duration = _duration(sources.video)
    cues = subtitles.read(sources.subtitles)

    detected = None
    detection = None
    if sources.full_mix and sources.no_dialogue:
        detection = speechtrack.detect(sources.full_mix, sources.no_dialogue)
        detected = detection.speech

    placement = plan.build(duration, cues, detected, policy=policy)
    slots = placement.slots[:limit] if limit else placement.slots

    cache = Cache(os.path.join(work, "written.json"))
    shot_dir = os.path.join(work, "frames")

    lines: list[Line] = []
    name = getattr(writer, "name", "writer")
    skipped = 0
    trimmed = 0
    dropped = 0
    rewritten = 0
    renamed = 0
    spoilers = 0
    for slot in slots:
        shots: list[str] = []

        def ask(attempt: int, too_long: str = "",
                forbidden: list[str] | None = None) -> str:
            """One request for this slot, remembered so a re-run is free."""
            key = Cache.key(name, slot.start, slot.budget, attempt)
            remembered = cache.get(key)
            if remembered is not None:
                return remembered
            if not shots:
                shots.extend(shot.path for shot in frames.across(
                    sources.video, slot.start, slot.budget, shot_dir,
                    count=frames_per_slot))
            before, after = nearby(cues, slot)
            # A retry is asked for a shorter line than the slot strictly
            # allows. Asking again for the same length tends to produce the
            # same length again, a few words rearranged.
            asked_for = slot.budget * (0.78 if too_long else 1.0)
            written = writer.write(vision.Request(
                start=slot.start, budget=asked_for, shots=shots,
                before=before, after=after, too_long=too_long,
                forbidden=forbidden or [],
                said_already=[line.text for line in lines],
            ))
            cache.put(key, written)
            return written

        text = ask(0)
        if not text or text.strip().upper().startswith("SKIP"):
            skipped += 1
            continue

        # A line that does not fit is sent back to be rewritten before it is
        # cut. A writer asked for a shorter sentence returns a sentence; a
        # sentence chopped at the tail returns a fragment.
        if not speech.fits(text, slot.budget, calibration):
            shorter = ask(1, too_long=text)
            if shorter and not shorter.strip().upper().startswith("SKIP"):
                if speech.fits(shorter, slot.budget, calibration):
                    rewritten += 1
                    text = shorter
                elif speech.duration(shorter, calibration) < speech.duration(
                        text, calibration):
                    text = shorter

        # A name the film has not said yet is a spoiler, so it is asked for
        # again without it. If the second answer leaks a name too, the line
        # is thrown away: saying nothing costs a listener a description,
        # while saying "Vesper" costs them the film.
        leaked = names.leaks(text, cues, slot.start)
        if leaked:
            clean = ask(2, forbidden=sorted(leaked))
            if (clean and not clean.strip().upper().startswith("SKIP")
                    and not names.leaks(clean, cues, slot.start)):
                renamed += 1
                text = clean
            else:
                spoilers += 1
                continue

        fitted = speech.trim(text, slot.budget, calibration)
        if not fitted:
            # Nothing survived that was still worth hearing. Silence is a
            # better answer than a fragment.
            dropped += 1
            continue
        if len(fitted.split()) * 2 < len(text.split()):
            # More than half the line was cut away. What is left is usually
            # a stub -- "Thom kisses his." -- and a listener is better served
            # by the silence it would have filled.
            dropped += 1
            continue
        was_trimmed = fitted != text
        trimmed += int(was_trimmed)
        lines.append(Line(
            start=slot.start, budget=slot.budget, text=fitted,
            estimated_seconds=speech.duration(fitted, calibration),
            trimmed=was_trimmed,
        ))

    track = Track(film=sources.name, duration=duration, lines=lines)
    track.generator = {
        "writer": getattr(writer, "name", "writer"),
        "frames_per_slot": frames_per_slot,
        "policy": policy.__dict__,
        "calibration": calibration.__dict__,
        "sources": placement.sources,
    }
    track.stats = _stats(placement, track, detection, skipped, trimmed, dropped,
                         rewritten, renamed, spoilers)
    return track


def _stats(placement: plan.Plan, track: Track, detection, skipped: int,
           trimmed: int, dropped: int, rewritten: int = 0, renamed: int = 0,
           spoilers: int = 0) -> dict:
    """Everything worth publishing about this run, computed, not claimed."""
    stats = placement.summary()
    stats.update({
        "lines_written": len(track.lines),
        "lines_skipped_by_writer": skipped,
        "lines_dropped_as_too_long": dropped,
        "lines_rewritten_shorter": rewritten,
        "lines_rewritten_without_a_premature_name": renamed,
        "lines_dropped_as_spoilers": spoilers,
        "lines_trimmed_to_fit": trimmed,
        "words_spoken": track.words(),
        "speaking_seconds": track.speaking_seconds(),
        "share_of_silence_used": round(
            track.speaking_seconds() / placement.silent, 4)
        if placement.silent else 0,
        "smallest_headroom_seconds": round(
            min((line.headroom for line in track.lines), default=0), 3),
    })
    if detection is not None:
        spoken = {line.start: line.spoken for line in track.lines}
        hits = plan.collisions(
            [gaps.Slot(line.start, line.spoken, False, False)
             for line in track.lines], detection.speech, spoken)
        stats.update({
            "audio_speech_seconds": round(
                sum(span.duration for span in detection.speech), 2),
            "audio_stem_separation_db": detection.separation_db,
            "collisions_with_measured_speech": len(hits),
            "collision_detail": hits[:10],
        })
    return stats


def _duration(video: str) -> float:
    """The film's running time, from the file rather than from the subtitles."""
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video],
        capture_output=True, text=True, check=True)
    return round(float(result.stdout.strip()), 3)

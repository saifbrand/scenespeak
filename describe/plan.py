"""Decide where a film's descriptions go, and report what that cost.

Placement is planned against everything known about when the film talks.
Subtitles are always available and are the usual answer. They are also, on
their own, wrong often enough to matter: measured on Tears of Steel, real
speech runs past the end of its own cue by up to 1.07 seconds, and 13.8
seconds of the film is spoken with no subtitle at all. Planning from the
subtitle file alone put 3 of 49 descriptions on top of a voice.

So when a film's audio can be analysed (see `speechtrack`), what it finds is
merged into the dialogue map rather than used only to grade it afterwards.
The verification then still means something, because it is checking a
different question: not "did we obey the map" but "is the map right".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from describe import gaps, subtitles
from describe.subtitles import Cue, Span


@dataclass(frozen=True)
class Plan:
    """Where descriptions may be spoken, and the arithmetic behind it."""

    duration: float
    slots: list[gaps.Slot]
    dialogue: list[Span]
    sources: list[str]
    """Which evidence the dialogue map was built from, named for the record."""

    @property
    def talking(self) -> float:
        return sum(span.duration for span in self.dialogue)

    @property
    def silent(self) -> float:
        return self.duration - self.talking

    @property
    def budget(self) -> float:
        """Total speaking room the descriptions have across the film."""
        return sum(slot.budget for slot in self.slots)

    def summary(self) -> dict:
        return {
            "duration_seconds": round(self.duration, 2),
            "dialogue_seconds": round(self.talking, 2),
            "silent_seconds": round(self.silent, 2),
            "silent_share": round(self.silent / self.duration, 4) if self.duration else 0,
            "slots": len(self.slots),
            "speaking_budget_seconds": round(self.budget, 2),
            "sources": list(self.sources),
        }


def union(*groups: list[Span]) -> list[Span]:
    """Merge several sets of spans into one non-overlapping timeline.

    Union, never intersection. Two sources disagreeing about whether the
    film is talking is not a reason to assume it is quiet.
    """
    everything = sorted((span for group in groups for span in group),
                        key=lambda span: span.start)
    merged: list[Span] = []
    for span in everything:
        if merged and span.start <= merged[-1].end:
            merged[-1] = Span(merged[-1].start, max(merged[-1].end, span.end))
        else:
            merged.append(span)
    return merged


def build(duration: float, cues: list[Cue], speech: list[Span] | None = None,
          policy: gaps.Policy = gaps.Policy(), join_below: float = 0.6) -> Plan:
    """Work out the description slots for one film."""
    sources = ["subtitles"]
    talking = subtitles.dialogue(cues, join_below=join_below)
    if speech:
        sources.append("audio")
        talking = union(talking, speech)
        talking = subtitles.dialogue(
            [Cue(span.start, span.end, "-") for span in talking],
            join_below=join_below,
        )
    return Plan(duration=duration, slots=gaps.slots(talking, duration, policy),
                dialogue=talking, sources=sources)


def collisions(slots: list[gaps.Slot], speech: list[Span],
               spoken: dict[float, float] | None = None) -> list[dict]:
    """Every description that overlaps speech, with how badly.

    `spoken` maps a slot's start time to the measured duration of the line
    actually placed in it, so the check can be run against real synthesised
    audio rather than against the budget the slot was allowed. Without it
    the whole budget is assumed used, which is the strictest reading.
    """
    found: list[dict] = []
    for slot in slots:
        end = slot.start + (spoken.get(slot.start, slot.budget) if spoken
                            else slot.budget)
        for span in speech:
            if slot.start < span.end and end > span.start:
                found.append({
                    "slot_start": round(slot.start, 3),
                    "slot_end": round(end, 3),
                    "speech_start": round(span.start, 3),
                    "speech_end": round(span.end, 3),
                    "overlap_seconds": round(
                        min(end, span.end) - max(slot.start, span.start), 3),
                })
    return found

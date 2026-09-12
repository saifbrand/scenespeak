"""Find the openings in a film where a description may be spoken.

The whole program rests on one rule: a description may never talk over
dialogue. Everything in this module is that rule turned into arithmetic.
A gap between two lines of dialogue is not automatically an opening — it
has to be long enough to say anything useful in, and it has to be trimmed
at both ends so that a slow voice or a late-starting engine still lands
inside the quiet.
"""
from __future__ import annotations

import math

from dataclasses import dataclass

from describe.subtitles import Span


@dataclass(frozen=True)
class Policy:
    """The margins a description is held to. All values in seconds.

    The two lead values are not symmetric, and the asymmetry is the point.
    Starting a moment late is harmless — the description simply says less.
    Finishing late means talking over the next line, which is the failure
    this program exists to prevent, so the tail margin is the larger one.
    """

    lead_in: float = 0.4
    """Quiet to leave after dialogue ends before a description may begin."""

    lead_out: float = 0.8
    """Quiet that must remain between a description ending and dialogue
    resuming. Absorbs a late-starting synthesiser and a trailing breath."""

    minimum: float = 1.6
    """Shorter than this and nothing worth hearing fits, so the gap is left
    alone rather than filled with a fragment."""

    longest: float = 12.0
    """No single description may run longer than this, however long the
    silence is. Past it a listener has lost the thread, and a description
    that long is a summary, not a description."""

    rest: float = 3.0
    """Quiet left between two descriptions inside one long silence. Without
    it a wordless sequence becomes a lecture."""


@dataclass(frozen=True)
class Slot:
    """An opening a description may be written for.

    `budget` is the hard limit the words have to fit inside; `start` is when
    speech begins. The player stops the voice at `start + budget` no matter
    what, so a line that overruns is cut off rather than allowed to bleed
    into the next spoken word.
    """

    start: float
    budget: float
    after_dialogue: bool
    before_dialogue: bool

    @property
    def end(self) -> float:
        return self.start + self.budget


def silences(dialogue: list[Span], duration: float) -> list[Span]:
    """The complement of dialogue across the whole running time.

    Spans are assumed sorted and non-overlapping, which is what
    `subtitles.dialogue` produces. Anything past the end of the film is
    clipped: a subtitle file that runs long should not invent screen time.
    """
    quiet: list[Span] = []
    cursor = 0.0
    for span in dialogue:
        if span.start > cursor:
            quiet.append(Span(cursor, min(span.start, duration)))
        cursor = max(cursor, span.end)
        if cursor >= duration:
            break
    if cursor < duration:
        quiet.append(Span(cursor, duration))
    return [span for span in quiet if span.duration > 0]


def slots(dialogue: list[Span], duration: float,
          policy: Policy = Policy()) -> list[Slot]:
    """Turn a film's silences into the openings a description may use.

    Each silence is pulled in by the lead margins first, then cut into as
    many slots as fit with a rest between them. The margins are applied only
    where there is actually dialogue to protect: the quiet before the first
    line and after the last one needs no guard against speech that is not
    there, and those two stretches are often the best description of all —
    the establishing shot and the final image.
    """
    found: list[Slot] = []
    for span in silences(dialogue, duration):
        after = span.start > 0
        before = span.end < duration
        start = span.start + (policy.lead_in if after else 0.0)
        limit = span.end - (policy.lead_out if before else 0.0)

        first = True
        while limit - start >= policy.minimum:
            # Times are rounded to milliseconds so the track is readable,
            # and only ever in the direction that keeps the margin. The
            # order matters: the start is rounded first, later, and the
            # budget is then measured from where the slot actually begins
            # and rounded shorter. Rounding them independently gives back
            # time at one end and takes it at the other, which a randomised
            # test caught as a slot ending 0.7996s before the next line
            # instead of the 0.8 the policy promises.
            begins = _up(start)
            budget = _down(min(policy.longest, limit - begins))
            if budget < policy.minimum:
                break
            found.append(Slot(start=begins, budget=budget,
                              after_dialogue=after and first,
                              before_dialogue=before))
            start = begins + budget + policy.rest
            first = False
    return found


def _up(seconds: float) -> float:
    return math.ceil(seconds * 1000) / 1000


def _down(seconds: float) -> float:
    return math.floor(seconds * 1000) / 1000

"""Read a film's subtitles as intervals of dialogue.

Subtitles are the only machine-readable record of when a film talks that
ships with almost every title, so they are what a description track has to
be planned against. They are a *proxy*, not the truth: a cue can appear a
beat before the line is spoken and linger after it, and silence between two
cues may still be full of music. Everything downstream therefore treats a
cue as "dialogue is happening here, probably a little wider than reality",
and the placement is checked against the real audio in `verify.py` before
any number is published.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 00:01:02,500 --> 00:01:04,000, with the optional cue-position fields that
# some authoring tools append ("X1:000 X2:000 Y1:050 Y2:100") ignored.
TIMING = re.compile(
    r"(?P<sh>\d+):(?P<sm>\d{1,2}):(?P<ss>\d{1,2})[,.](?P<sms>\d{1,3})"
    r"\s*-->\s*"
    r"(?P<eh>\d+):(?P<em>\d{1,2}):(?P<es>\d{1,2})[,.](?P<ems>\d{1,3})"
)
TAGS = re.compile(r"</?[a-zA-Z][^>]*>")


@dataclass(frozen=True)
class Cue:
    """One subtitle: when it is on screen, and what it says."""

    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Span:
    """A stretch of time with nothing else said about it."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse(text: str) -> list[Cue]:
    """Parse SRT into cues, in time order.

    Deliberately forgiving. Real subtitle files in the wild carry a BOM,
    CRLF endings, missing or repeated index numbers, blank cues used as
    spacers, and formatting tags. None of that changes when the film talks,
    so none of it is allowed to stop the parse. A block whose timing line
    cannot be read is skipped rather than guessed at: inventing a timestamp
    would put a description on top of speech, which is the one thing this
    program exists to prevent.
    """
    cues: list[Cue] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.lstrip("﻿")):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        timing = None
        for index, line in enumerate(lines):
            match = TIMING.search(line)
            if match:
                timing, body = match, lines[index + 1:]
                break
        if timing is None:
            continue
        start = _seconds(timing["sh"], timing["sm"], timing["ss"], timing["sms"])
        end = _seconds(timing["eh"], timing["em"], timing["es"], timing["ems"])
        if end < start:
            start, end = end, start
        said = clean(" ".join(body))
        if said:
            cues.append(Cue(start=start, end=end, text=said))
    cues.sort(key=lambda cue: (cue.start, cue.end))
    return cues


def clean(text: str) -> str:
    """Strip markup and collapse whitespace, keeping the words themselves."""
    return re.sub(r"\s+", " ", TAGS.sub("", text)).strip()


def read(path: str) -> list[Cue]:
    """Read a subtitle file, whatever encoding it happens to be in.

    Subtitle files are routinely Latin-1 or cp1252 despite what they claim.
    Falling back keeps a film usable instead of failing on one accent.
    """
    with open(path, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return parse(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    return parse(raw.decode("utf-8", errors="replace"))


def dialogue(cues: list[Cue], join_below: float = 0.0) -> list[Span]:
    """Merge cues into the stretches during which the film is talking.

    Overlapping and touching cues become one span. `join_below` additionally
    swallows the tiny gaps between consecutive lines of the same exchange:
    a third of a second of quiet between two people is not an opening for a
    description, it is the middle of a conversation, and treating it as an
    opening is how a description ends up interrupting one.
    """
    spans: list[Span] = []
    for cue in sorted(cues, key=lambda cue: cue.start):
        if spans and cue.start - spans[-1].end <= join_below:
            last = spans.pop()
            spans.append(Span(last.start, max(last.end, cue.end)))
        else:
            spans.append(Span(cue.start, cue.end))
    return spans

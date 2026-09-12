"""Find where a film actually talks, from its audio rather than its subtitles.

Subtitles say when a line is *displayed*, which is close to when it is
spoken but not the same thing, and they are the only thing the placement
pipeline gets to see. That makes them a poor judge of their own work. This
module produces an independent answer, so the claim "no description ever
overlaps speech" can be checked against the film instead of against the
file the placement was derived from.

The method needs a film that ships a music-and-effects stem alongside its
full mix -- as the Blender open movies do. Subtracting one from the other
does not work: they are separate renders, misaligned by a few milliseconds
and mastered differently, so the difference of the waveforms is mostly
mastering. What survives that is a *comparison in the speech band*. Both
mixes carry the same music and effects, so the music cancels out of the
comparison, and whatever extra energy the full mix has between 300 Hz and
3.4 kHz is a voice. Measured on Tears of Steel, that difference averages
+7.5 dB where the subtitles say someone is talking and 0.0 dB where they
say nobody is.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

import numpy as np

from describe.subtitles import Span

RATE = 16000
WINDOW = 512      # 32 ms
HOP = 160         # 10 ms
LOW, HIGH = 300, 3400   # the band a human voice lives in


@dataclass(frozen=True)
class Detection:
    """Speech found in the audio, with the evidence that found it."""

    speech: list[Span]
    lag_seconds: float
    """How far the stem had to be shifted to line up with the full mix."""
    separation_db: float
    """Median extra speech-band energy inside the detected speech. Small
    numbers mean the two files are not the pair this method needs."""


def decode(path: str, cache: str = ".cache") -> np.ndarray:
    """Decode any audio file to mono 16 kHz floats, caching the result."""
    os.makedirs(cache, exist_ok=True)
    raw = os.path.join(cache, os.path.basename(path) + f".{RATE}.raw")
    if not os.path.exists(raw) or os.path.getmtime(raw) < os.path.getmtime(path):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", path,
             "-ac", "1", "-ar", str(RATE), "-f", "f32le", raw],
            check=True,
        )
    return np.fromfile(raw, dtype=np.float32)


def band_energy(signal: np.ndarray) -> np.ndarray:
    """Energy per 10 ms frame inside the speech band, in decibels."""
    frames = (len(signal) - WINDOW) // HOP
    if frames <= 0:
        return np.zeros(0)
    index = np.arange(WINDOW)[None, :] + HOP * np.arange(frames)[:, None]
    windowed = signal[index] * np.hanning(WINDOW)
    power = np.abs(np.fft.rfft(windowed, axis=1)) ** 2
    freqs = np.fft.rfftfreq(WINDOW, 1 / RATE)
    chosen = (freqs >= LOW) & (freqs <= HIGH)
    return 10 * np.log10(power[:, chosen].sum(axis=1) + 1e-12)


def align(full: np.ndarray, stem: np.ndarray, at: float = 60.0,
          seconds: float = 4.0) -> int:
    """Samples the stem must be shifted by to line up with the full mix."""
    window = slice(int(at * RATE), int((at + seconds) * RATE))
    x = full[window].astype(np.float64)
    y = stem[window].astype(np.float64)
    if x.size == 0 or y.size == 0:
        return 0
    correlation = np.correlate(x - x.mean(), y - y.mean(), "full")
    return int(correlation.argmax() - (len(y) - 1))


def detect(full_mix: str, no_dialogue: str, enter_db: float = 6.0,
           stay_db: float = 2.0, shortest: float = 0.20,
           join_below: float = 0.25) -> Detection:
    """Where the voice is, by comparing the full mix with the stem.

    Two thresholds rather than one: a frame has to be clearly louder than
    the stem to start a stretch of speech, but only slightly louder to
    continue it. A single threshold chops one sentence into a dozen
    fragments every time the speaker takes a breath, and fragments make
    the silence between them look like an opening for a description.
    """
    full = decode(full_mix)
    stem = decode(no_dialogue)
    shift = align(full, stem)
    stem = np.roll(stem, shift)
    size = min(len(full), len(stem))

    delta = band_energy(full[:size]) - band_energy(stem[:size])
    delta = delta - np.median(delta)   # the two renders sit at different levels

    loud = delta >= enter_db
    holding = delta >= stay_db
    speaking = np.zeros(len(delta), dtype=bool)
    active = False
    for index in range(len(delta)):
        active = loud[index] if not active else holding[index]
        speaking[index] = active

    spans = _runs(speaking, HOP / RATE)
    spans = _join(spans, join_below)
    spans = [span for span in spans if span.duration >= shortest]

    inside = np.zeros(len(delta), dtype=bool)
    for span in spans:
        inside[int(span.start * RATE / HOP):int(span.end * RATE / HOP)] = True
    separation = float(np.median(delta[inside])) if inside.any() else 0.0

    return Detection(speech=spans, lag_seconds=shift / RATE,
                     separation_db=round(separation, 2))


def _runs(flags: np.ndarray, step: float) -> list[Span]:
    """Turn a per-frame boolean into the spans where it is true."""
    spans: list[Span] = []
    start = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            spans.append(Span(start * step, index * step))
            start = None
    if start is not None:
        spans.append(Span(start * step, len(flags) * step))
    return spans


def _join(spans: list[Span], below: float) -> list[Span]:
    merged: list[Span] = []
    for span in spans:
        if merged and span.start - merged[-1].end <= below:
            merged[-1] = Span(merged[-1].start, span.end)
        else:
            merged.append(span)
    return merged

"""Finding speech in the audio.

The detector's job is to disagree with the subtitles when the subtitles are
wrong. These tests cover the parts that can be checked without a film: how
a run of loud frames becomes a span, how breaths are joined, and that the
alignment search finds a shift it was given.
"""
from __future__ import annotations

import numpy as np

from describe import speechtrack
from describe.subtitles import Span


def test_a_run_of_true_becomes_one_span():
    flags = np.array([False, True, True, True, False])
    spans = speechtrack._runs(flags, 0.1)
    assert [(round(s.start, 2), round(s.end, 2)) for s in spans] == [(0.1, 0.4)]


def test_speech_running_to_the_very_end_is_still_closed():
    spans = speechtrack._runs(np.array([False, True, True]), 0.1)
    assert [(round(s.start, 2), round(s.end, 2)) for s in spans] == [(0.1, 0.3)]


def test_nothing_loud_is_no_speech():
    assert speechtrack._runs(np.array([False, False]), 0.1) == []


def test_a_breath_inside_a_sentence_is_joined_up():
    spans = [Span(0, 1), Span(1.1, 2), Span(5, 6)]
    joined = speechtrack._join(spans, below=0.25)
    assert [(s.start, s.end) for s in joined] == [(0, 2), (5, 6)]


def test_a_real_pause_is_left_alone():
    joined = speechtrack._join([Span(0, 1), Span(3, 4)], below=0.25)
    assert len(joined) == 2


def test_band_energy_is_higher_for_a_voice_band_tone_than_for_a_rumble():
    time = np.arange(speechtrack.RATE) / speechtrack.RATE
    speech_band = np.sin(2 * np.pi * 1000 * time).astype(np.float32)
    rumble = np.sin(2 * np.pi * 60 * time).astype(np.float32)
    assert speechtrack.band_energy(speech_band).mean() > \
        speechtrack.band_energy(rumble).mean() + 20


def test_alignment_finds_a_shift_it_was_given():
    rng = np.random.default_rng(7)
    signal = rng.standard_normal(speechtrack.RATE * 70).astype(np.float32)
    shifted = np.roll(signal, 120)
    assert speechtrack.align(signal, shifted) == -120


def test_alignment_of_something_with_itself_is_zero():
    rng = np.random.default_rng(11)
    signal = rng.standard_normal(speechtrack.RATE * 70).astype(np.float32)
    assert speechtrack.align(signal, signal) == 0


def test_band_energy_of_silence_does_not_blow_up():
    # A logarithm of zero would be minus infinity, and one silent frame
    # would then poison every median in the module.
    quiet = np.zeros(speechtrack.RATE, dtype=np.float32)
    energies = speechtrack.band_energy(quiet)
    assert np.isfinite(energies).all()

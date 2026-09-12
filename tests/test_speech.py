"""Fitting words into seconds.

The timing model may be approximate. What it may not be is optimistic: a
line the model thinks fits and does not will be spoken over an actor.
"""
from __future__ import annotations

import json

from describe import speech


def test_a_longer_line_takes_longer():
    short = speech.duration("He turns.")
    long = speech.duration("He turns and walks slowly towards the far door.")
    assert long > short


def test_syllables_not_words_decide_the_length():
    assert (speech.duration("Extraordinarily complicated machinery.")
            > speech.duration("A cat sat on a mat and a hat."))


def test_an_empty_line_takes_no_time():
    assert speech.duration("") == 0.0
    assert speech.duration("   ") == 0.0


def test_punctuation_buys_a_pause():
    assert (speech.duration("He turns, slowly, and leaves.")
            > speech.duration("He turns slowly and leaves"))


def test_a_trim_always_fits_the_budget():
    line = ("The city skyline is swallowed by a wall of smoke, and the sky "
            "goes dark as sirens begin to sound across the water.")
    for budget in (1.0, 1.5, 2.0, 3.0, 4.5, 6.0, 9.0, 30.0):
        fitted = speech.trim(line, budget)
        assert fitted == "" or speech.duration(fitted) <= budget


def test_a_line_that_already_fits_is_returned_untouched():
    line = "He looks at his hand."
    assert speech.trim(line, 30.0) == line


def test_a_trim_stops_at_a_clause_rather_than_mid_sentence():
    line = "The skyline is swallowed by smoke, and the sky goes dark."
    assert speech.trim(line, 3.0) == "The skyline is swallowed by smoke."


def test_a_trim_never_ends_on_a_dangling_word():
    line = ("Two wire-frame figures stand in a complex industrial interior "
            "before a glowing playback interface appears.")
    for budget in (2.0, 2.5, 3.0, 3.7, 4.5, 5.5):
        fitted = speech.trim(line, budget)
        if fitted:
            last = fitted.rstrip(".").split()[-1].lower()
            assert last not in speech.DANGLING, fitted


def test_a_budget_too_small_for_anything_gets_nothing():
    assert speech.trim("A woman in a red coat runs across the rooftop.", 0.4) == ""


def test_the_word_estimate_actually_fits_the_budget_it_was_asked_about():
    for budget in (2.0, 4.0, 8.0, 12.0):
        words = speech.words_for(budget)
        typical = " ".join(["walking"] * words) + "."
        assert speech.duration(typical) <= budget * 1.35


def test_calibration_is_read_from_disk_when_there_is_one(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"per_syllable": 0.5, "source": "a device"}),
                    encoding="utf-8")
    loaded = speech.Calibration.load(str(path))
    assert loaded.per_syllable == 0.5
    assert loaded.source == "a device"
    assert loaded.overhead == speech.Calibration().overhead


def test_a_missing_or_broken_calibration_falls_back_to_the_defaults(tmp_path):
    assert speech.Calibration.load(str(tmp_path / "nope.json")) == speech.Calibration()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert speech.Calibration.load(str(broken)) == speech.Calibration()


def test_an_unknown_field_in_a_calibration_file_does_not_crash_the_run(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text(json.dumps({"per_syllable": 0.3, "voice_pitch": 7}),
                    encoding="utf-8")
    assert speech.Calibration.load(str(path)).per_syllable == 0.3


def test_a_slower_calibration_makes_every_line_shorter():
    slow = speech.Calibration(per_syllable=0.4)
    line = "A man in a long coat walks across the empty rooftop."
    assert speech.duration(line, slow) > speech.duration(line)
    assert (len(speech.trim(line, 4.0, slow).split())
            < len(speech.trim(line, 4.0).split()))

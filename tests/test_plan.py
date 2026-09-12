"""Planning against everything known about when the film talks.

The measurement that justifies this module: on Tears of Steel, real speech
runs past the end of its own subtitle cue by up to 1.07 seconds, and 13.8
seconds of the film is spoken with no subtitle at all. Planning from the
subtitle file alone put descriptions on top of a voice three times.
"""
from __future__ import annotations

from describe import gaps, plan
from describe.subtitles import Cue, Span


def cues(*triples: tuple[float, float, str]) -> list[Cue]:
    return [Cue(start, end, text) for start, end, text in triples]


def test_two_sources_are_merged_not_intersected():
    merged = plan.union([Span(0, 5), Span(10, 12)], [Span(4, 7), Span(20, 21)])
    assert [(span.start, span.end) for span in merged] == [(0, 7), (10, 12), (20, 21)]


def test_a_disagreement_is_resolved_towards_silence_being_speech():
    # If one source says the film is talking, that settles it. Assuming the
    # quiet one is right is how a description lands on a line of dialogue.
    merged = plan.union([Span(10, 11)], [])
    assert [(span.start, span.end) for span in merged] == [(10, 11)]


def test_touching_spans_become_one():
    merged = plan.union([Span(0, 5)], [Span(5, 9)])
    assert len(merged) == 1


def test_a_plan_from_subtitles_alone_says_so():
    made = plan.build(60, cues((10, 12, "Hello.")))
    assert made.sources == ["subtitles"]
    assert made.summary()["sources"] == ["subtitles"]


def test_a_plan_that_used_the_audio_says_so_too():
    made = plan.build(60, cues((10, 12, "Hello.")), [Span(30, 31)])
    assert made.sources == ["subtitles", "audio"]


def test_speech_the_subtitles_missed_removes_a_slot_that_would_have_collided():
    """The finding that made this project worth building, as a test."""
    said = cues((10, 12, "Hello."))
    unsubtitled = [Span(20, 24)]

    blind = plan.build(60, said)
    assert plan.collisions(blind.slots, unsubtitled), (
        "a plan made from subtitles alone should walk straight into "
        "unsubtitled speech")

    seeing = plan.build(60, said, unsubtitled)
    assert plan.collisions(seeing.slots, unsubtitled) == []


def test_a_collision_reports_how_much_of_it_there_is():
    found = plan.collisions([gaps.Slot(10.0, 5.0, False, False)], [Span(12, 20)])
    assert found[0]["overlap_seconds"] == 3.0


def test_the_measured_length_of_a_line_is_used_when_it_is_known():
    # The slot allows five seconds; the line took two. Judging it by the
    # budget would report a collision that never happened.
    slot = gaps.Slot(10.0, 5.0, False, False)
    assert plan.collisions([slot], [Span(13, 20)])
    assert plan.collisions([slot], [Span(13, 20)], spoken={10.0: 2.0}) == []


def test_the_summary_adds_up():
    made = plan.build(100, cues((10, 20, "Talking.")))
    summary = made.summary()
    assert summary["dialogue_seconds"] == 10.0
    assert summary["silent_seconds"] == 90.0
    assert summary["silent_share"] == 0.9
    assert summary["slots"] == len(made.slots)


def test_a_film_that_is_all_dialogue_has_no_silence_and_no_slots():
    made = plan.build(20, cues((0, 20, "Nonstop.")))
    assert made.silent == 0
    assert made.slots == []
    assert made.summary()["silent_share"] == 0.0

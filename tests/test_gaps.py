"""The rule, stated as tests.

A description may never be spoken over dialogue. Everything else in this
project is a convenience; this is the thing it must not get wrong, so it is
checked here directly, on ordinary cases and on randomly generated films.
"""
from __future__ import annotations

import random

from describe import gaps
from describe.subtitles import Span


def spans(*pairs: tuple[float, float]) -> list[Span]:
    return [Span(start, end) for start, end in pairs]


def test_the_quiet_between_two_lines_becomes_an_opening():
    found = gaps.slots(spans((0, 2), (20, 22)), 30)
    assert found
    first = found[0]
    assert first.start == 2.4          # 2.0 + lead_in
    assert round(first.end, 3) == 14.4  # capped at the longest single line


def test_a_short_gap_is_left_alone():
    # A second of quiet cannot hold anything worth hearing.
    assert gaps.slots(spans((0, 5), (6, 10)), 10) == []


def test_nothing_ever_overlaps_dialogue():
    dialogue = spans((10, 14), (30, 33), (50, 60))
    for slot in gaps.slots(dialogue, 90):
        for span in dialogue:
            assert not (slot.start < span.end and slot.end > span.start)


def test_a_margin_is_left_before_speech_resumes():
    dialogue = spans((0, 1), (40, 45))
    for slot in gaps.slots(dialogue, 60):
        if slot.end <= 40:
            assert slot.end <= 40 - gaps.Policy().lead_out + 1e-9


def test_the_opening_shot_needs_no_guard_against_speech_that_has_not_started():
    # The establishing shot is often the most useful description in a film,
    # and there is nothing before it to talk over.
    first = gaps.slots(spans((30, 35)), 60)[0]
    assert first.start == 0.0


def test_a_long_silence_is_broken_into_several_descriptions_with_rests():
    policy = gaps.Policy()
    found = gaps.slots(spans((0, 1)), 120)
    assert len(found) > 1
    assert all(slot.budget <= policy.longest + 1e-9 for slot in found)
    for earlier, later in zip(found, found[1:]):
        assert round(later.start - earlier.end, 3) >= policy.rest - 1e-9


def test_a_film_with_no_dialogue_at_all_is_still_described():
    assert gaps.slots([], 60)


def test_a_film_that_never_stops_talking_gets_nothing():
    assert gaps.slots(spans((0, 60)), 60) == []


def test_subtitles_running_past_the_end_of_the_film_do_not_invent_screen_time():
    for slot in gaps.slots(spans((0, 5), (50, 900)), 60):
        assert slot.end <= 60


def test_the_rule_holds_on_a_thousand_random_films():
    """The margins are arithmetic, and arithmetic should be checked at scale.

    Hand-written cases test the shapes somebody thought of. This tests the
    shapes nobody thought of: films that open talking, films that end
    talking, dialogue that repeats, gaps of every length.
    """
    rng = random.Random(20261023)
    policy = gaps.Policy()
    for _ in range(1000):
        duration = rng.uniform(20, 600)
        dialogue: list[Span] = []
        cursor = rng.uniform(0, 10)
        while cursor < duration:
            length = rng.uniform(0.3, 12)
            dialogue.append(Span(cursor, min(cursor + length, duration)))
            cursor += length + rng.uniform(0.05, 25)
        dialogue = [span for span in dialogue if span.duration > 0]

        for slot in gaps.slots(dialogue, duration, policy):
            assert slot.budget >= policy.minimum - 1e-9
            assert slot.end <= duration + 1e-9
            for span in dialogue:
                assert not (slot.start < span.end and slot.end > span.start), (
                    f"{slot} overlaps {span}")
                if slot.end <= span.start:
                    assert span.start - slot.end >= policy.lead_out - 1e-6

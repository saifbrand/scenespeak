"""Nobody is named before the film names them.

The failure this prevents is real and was observed: writing Tears of Steel,
the model called a character "Vesper" in a line at 6:51, a name that appears
nowhere in the subtitles at any point. A listener would have been handed a
character's name by the accessibility track that no sighted viewer is given.
"""
from __future__ import annotations

from describe import names, subtitles

CUES = subtitles.parse(
    "1\n00:00:10,000 --> 00:00:12,000\nYou're a jerk, Thom.\n\n"
    "2\n00:01:00,000 --> 00:01:02,000\nHow's it looking, Barley?\n"
)


def test_a_name_the_dialogue_has_not_reached_yet_is_a_leak():
    assert names.leaks("Barley lifts the rope.", CUES, when=30.0) == {"Barley"}


def test_the_same_name_is_fine_once_the_film_has_said_it():
    assert names.leaks("Barley lifts the rope.", CUES, when=120.0) == set()


def test_a_name_spoken_in_dialogue_earlier_is_available_immediately_after():
    assert names.leaks("Thom raises the rifle.", CUES, when=13.0) == set()


def test_a_sentence_opening_with_the_is_not_a_name():
    assert names.leaks("The man lowers his arms.", CUES, when=5.0) == set()


def test_a_cast_name_at_the_start_of_a_description_is_caught_too():
    # "Barley" opens the sentence, so the only reason it is recognised as a
    # name at all is that the film's own dialogue uses it mid-sentence.
    assert names.leaks("Barley hauls the rope.", CUES, when=5.0) == {"Barley"}


def test_the_film_teaches_the_checker_its_own_cast():
    assert names.cast(CUES) == {"thom", "barley"}


def test_a_name_the_film_never_says_is_caught_mid_sentence():
    assert names.leaks("A man waits as Vesper enters.", CUES, when=5.0) == {"Vesper"}


def test_a_name_the_film_never_says_slips_through_at_a_sentence_start():
    # The documented limit of the backstop: with no dialogue anywhere that
    # uses "Vesper" as a name, an opening word cannot be told apart from
    # "Smoke fills the room". The writer is instructed about this as well,
    # which is what covers the case.
    assert names.leaks("Vesper watches.", CUES, when=5.0) == set()


def test_an_ordinary_noun_opening_a_sentence_is_not_treated_as_a_name():
    assert names.leaks("Smoke fills the room.", CUES, when=5.0) == set()


def test_ordinary_capitalised_words_are_not_mistaken_for_people():
    line = "The Earth turns as Monday's light reaches the window."
    assert names.leaks(line, CUES, when=5.0) == set()


def test_a_possessive_does_not_hide_a_name():
    assert names.leaks("The rope pulls Barley's arm down.", CUES, when=5.0) == {"Barley's"}


def test_the_check_is_case_insensitive_about_what_counts_as_known():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000\nTHOM, look out.\n")
    assert names.leaks("Thom ducks.", cues, when=10.0) == set()

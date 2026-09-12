"""Reading subtitles, including the ones written by hand at 3am.

A subtitle file is the only input this program cannot choose. It arrives as
whatever the film shipped with, and the parser is not allowed to be the
reason a film cannot be described.
"""
from __future__ import annotations

from describe import subtitles

SIMPLE = """1
00:00:01,000 --> 00:00:02,500
Hello there.

2
00:00:04,000 --> 00:00:05,000
General Kenobi.
"""


def test_a_plain_file_parses():
    cues = subtitles.parse(SIMPLE)
    assert [(cue.start, cue.end, cue.text) for cue in cues] == [
        (1.0, 2.5, "Hello there."),
        (4.0, 5.0, "General Kenobi."),
    ]


def test_a_bom_and_windows_line_endings_change_nothing():
    cues = subtitles.parse("﻿" + SIMPLE.replace("\n", "\r\n"))
    assert len(cues) == 2
    assert cues[0].text == "Hello there."


def test_formatting_tags_are_stripped_but_the_words_kept():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000\n"
                           "<i>Whispering</i> in the <b>dark</b>.\n")
    assert cues[0].text == "Whispering in the dark."


def test_a_cue_split_over_two_lines_becomes_one_line_of_speech():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000\n"
                           "You have your robotics,\nand I want space.\n")
    assert cues[0].text == "You have your robotics, and I want space."


def test_a_missing_index_number_is_not_fatal():
    cues = subtitles.parse("00:00:01,000 --> 00:00:02,000\nNo number here.\n")
    assert cues[0].text == "No number here."


def test_cue_position_fields_after_the_timing_are_ignored():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000  "
                           "X1:100 X2:600 Y1:400 Y2:480\nPositioned.\n")
    assert (cues[0].start, cues[0].text) == (1.0, "Positioned.")


def test_a_block_with_no_timing_is_skipped_rather_than_guessed_at():
    # Inventing a timestamp would place a description over speech, which is
    # the one outcome the whole program is built to prevent.
    cues = subtitles.parse("junk\nnot a timing\n\n1\n"
                           "00:00:01,000 --> 00:00:02,000\nReal.\n")
    assert [cue.text for cue in cues] == ["Real."]


def test_an_empty_cue_is_dropped():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000\n\n\n2\n"
                           "00:00:03,000 --> 00:00:04,000\nSomething.\n")
    assert [cue.text for cue in cues] == ["Something."]


def test_backwards_timings_are_straightened_not_believed():
    cues = subtitles.parse("1\n00:00:05,000 --> 00:00:02,000\nBackwards.\n")
    assert (cues[0].start, cues[0].end) == (2.0, 5.0)


def test_cues_come_back_in_time_order_however_they_were_written():
    cues = subtitles.parse("1\n00:00:09,000 --> 00:00:10,000\nSecond.\n\n"
                           "2\n00:00:01,000 --> 00:00:02,000\nFirst.\n")
    assert [cue.text for cue in cues] == ["First.", "Second."]


def test_hours_and_milliseconds_are_read_properly():
    cues = subtitles.parse("1\n01:02:03,450 --> 01:02:04,000\nLate.\n")
    assert cues[0].start == 3723.45


def test_a_latin1_file_is_read_rather_than_refused(tmp_path):
    path = tmp_path / "sub.srt"
    path.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nCaf\xe9 ferm\xe9.\n"
                     .encode("latin-1"))
    assert subtitles.read(str(path))[0].text == "Caf\xe9 ferm\xe9."


def test_overlapping_cues_become_one_stretch_of_dialogue():
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:05,000\nA.\n\n"
                           "2\n00:00:03,000 --> 00:00:07,000\nB.\n")
    spans = subtitles.dialogue(cues)
    assert [(span.start, span.end) for span in spans] == [(1.0, 7.0)]


def test_a_breath_between_two_lines_is_not_an_opening():
    # Half a second between two lines of the same exchange is the middle of
    # a conversation, not a gap a description may be dropped into.
    cues = subtitles.parse("1\n00:00:01,000 --> 00:00:02,000\nA.\n\n"
                           "2\n00:00:02,500 --> 00:00:04,000\nB.\n")
    assert len(subtitles.dialogue(cues, join_below=0.6)) == 1
    assert len(subtitles.dialogue(cues, join_below=0.0)) == 2

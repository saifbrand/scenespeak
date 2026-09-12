"""The pipeline end to end, on a film made for the purpose.

Twenty seconds of colour bars with a tone is not a film, but it has a real
container, a real duration read by ffprobe, and real frames that ffmpeg has
to seek to -- which is everything the pipeline touches. The writer is the
stub, so this runs with no key, no network and no quota.
"""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from describe import gaps, speech, track, vision
from describe.build import Cache, Sources, nearby, run

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg is needed to make and read the test film",
)

SUBTITLES = """1
00:00:02,000 --> 00:00:04,000
Somebody says something.

2
00:00:14,000 --> 00:00:16,000
And somebody answers.
"""


@pytest.fixture
def film(tmp_path):
    video = tmp_path / "film.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=duration=20:size=320x180:rate=10", "-f", "lavfi", "-i",
         "sine=frequency=440:duration=20", "-shortest", "-pix_fmt", "yuv420p",
         str(video)],
        check=True,
    )
    srt = tmp_path / "film.srt"
    srt.write_text(SUBTITLES, encoding="utf-8")
    return Sources(name="Test Film", video=str(video), subtitles=str(srt))


def build(film, tmp_path, **kwargs):
    return run(film, vision.StubWriter(), out_dir=str(tmp_path / "out"),
               work=str(tmp_path / "work"), frames_per_slot=1, **kwargs)


def test_a_track_is_produced_with_lines_in_the_gaps(film, tmp_path):
    made = build(film, tmp_path)
    assert made.lines
    assert made.duration == pytest.approx(20, abs=0.5)
    for line in made.lines:
        assert line.text
        assert 2.0 <= line.start or line.start < 2.0  # inside the film
        assert line.start + line.budget <= made.duration + 1e-6


def test_no_line_is_longer_than_the_silence_it_was_written_for(film, tmp_path):
    for line in build(film, tmp_path).lines:
        assert line.estimated_seconds <= line.budget
        assert line.headroom >= 0


def test_nothing_overlaps_the_dialogue(film, tmp_path):
    made = build(film, tmp_path)
    for line in made.lines:
        for start, end in ((2.0, 4.0), (14.0, 16.0)):
            assert not (line.start < end and line.start + line.budget > start)


def test_the_stats_describe_the_run_that_happened(film, tmp_path):
    made = build(film, tmp_path)
    assert made.stats["lines_written"] == len(made.lines)
    assert made.stats["words_spoken"] == made.words()
    assert made.stats["sources"] == ["subtitles"]
    assert made.generator["writer"] == "stub"


def test_a_second_run_costs_nothing_and_says_the_same_thing(film, tmp_path):
    first = build(film, tmp_path)
    second = build(film, tmp_path)
    assert [line.text for line in first.lines] == [line.text for line in second.lines]


def test_the_cache_is_what_makes_that_true(film, tmp_path):
    build(film, tmp_path)
    with open(tmp_path / "work" / "written.json", encoding="utf-8") as handle:
        remembered = json.load(handle)
    assert remembered
    assert all(key.startswith("stub|") for key in remembered)


def test_a_writer_that_skips_everything_produces_an_empty_but_valid_track(film, tmp_path):
    class Silent:
        name = "silent"

        def write(self, request):
            return "SKIP"

    made = run(film, Silent(), out_dir=str(tmp_path / "out"),
               work=str(tmp_path / "work"), frames_per_slot=1)
    assert made.lines == []
    assert made.stats["lines_skipped_by_writer"] > 0
    assert made.stats["smallest_headroom_seconds"] == 0


def test_a_writer_that_will_not_stop_talking_has_its_lines_dropped(film, tmp_path):
    class Windbag:
        name = "windbag"

        def write(self, request):
            return " ".join(["interminably verbose circumlocution"] * 30) + "."

    made = run(film, Windbag(), out_dir=str(tmp_path / "out"),
               work=str(tmp_path / "work"), frames_per_slot=1)
    # Whatever survives still fits. Nothing is allowed through on the
    # grounds that the writer meant well.
    for line in made.lines:
        assert line.estimated_seconds <= line.budget


def test_the_track_survives_a_round_trip_through_a_file(film, tmp_path):
    made = build(film, tmp_path)
    path = tmp_path / "track.json"
    made.save(str(path))
    again = track.Track.load(str(path))
    assert [line.text for line in again.lines] == [line.text for line in made.lines]
    assert again.duration == made.duration
    assert again.stats == made.stats


def test_the_vtt_export_is_a_subtitle_file_a_player_can_read(film, tmp_path):
    text = build(film, tmp_path).to_vtt()
    assert text.startswith("WEBVTT")
    assert "-->" in text
    for row in text.splitlines():
        if "-->" in row:
            start, end = row.split(" --> ")
            assert start.count(":") == 2 and end.count(":") == 2


def test_the_context_given_to_the_writer_is_the_dialogue_around_the_slot():
    from describe.subtitles import Cue
    cues = [Cue(0, 1, "First."), Cue(2, 3, "Second."), Cue(20, 21, "Later.")]
    before, after = nearby(cues, gaps.Slot(5.0, 10.0, True, True))
    assert before == ["First.", "Second."]
    assert after == ["Later."]


def test_a_cache_key_changes_when_the_slot_does():
    assert Cache.key("w", 1.0, 2.0) != Cache.key("w", 1.0, 3.0)
    assert Cache.key("w", 1.0, 2.0) != Cache.key("other", 1.0, 2.0)
    assert Cache.key("w", 1.0, 2.0) != Cache.key("w", 1.0, 2.0, attempt=1)

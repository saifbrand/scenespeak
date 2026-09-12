"""Pull the pictures a description is written from.

A slot is a stretch of time, not a moment, and things move. One frame from
the middle of an eight-second silence can miss the whole event -- a door
opening, someone drawing a weapon, a city collapsing. So a slot is sampled
several times across its own length and the writer is shown the sequence,
which is also the only way it can tell that something *changed* rather than
just listing what is on screen.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Shot:
    """One sampled frame: when it was taken and where the file is."""

    at: float
    path: str


def sample(video: str, at: float, path: str, width: int = 512) -> str:
    """Write a single frame to `path`, seeking before decoding.

    `-ss` in front of `-i` seeks on the container rather than decoding from
    the start of the film, which is the difference between a second and a
    minute per frame on a twelve-minute file.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", video,
         "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "4", path],
        check=True,
    )
    return path


def across(video: str, start: float, length: float, folder: str,
           count: int = 3, width: int = 512) -> list[Shot]:
    """Sample `count` frames spread across a slot.

    The first and last samples are pulled inward by a tenth of the slot so
    that a cut sitting exactly on the boundary does not hand back a frame
    from the shot next door.
    """
    if count < 1:
        return []
    if count == 1:
        offsets = [0.5]
    else:
        inset = 0.1
        step = (1 - 2 * inset) / (count - 1)
        offsets = [inset + step * index for index in range(count)]

    shots: list[Shot] = []
    for index, offset in enumerate(offsets):
        at = start + length * offset
        path = os.path.join(folder, f"{start:09.3f}_{index}.jpg")
        sample(video, at, path, width=width)
        shots.append(Shot(at=round(at, 3), path=path))
    return shots

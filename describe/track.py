"""The description track: what the player is given, and how it is written.

The file is plain JSON because it has to be read by an Android app, by a
test, and by a person checking the work by eye. Every line carries not just
its words but the room it was given and how long it is expected to take, so
that a reviewer can see the margin without running anything, and so the
player can hard-stop a line that turns out to run long on a voice nobody
calibrated for.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Line:
    """One spoken description."""

    start: float
    budget: float
    """Seconds of silence this line must finish inside."""
    text: str
    estimated_seconds: float
    """What the calibrated timing model expects this line to take."""
    measured_seconds: float = 0.0
    """What it actually took when synthesised, once that has been measured.
    Zero means not measured yet."""
    trimmed: bool = False
    """Whether the written line had to be shortened to fit."""

    @property
    def spoken(self) -> float:
        return self.measured_seconds or self.estimated_seconds

    @property
    def headroom(self) -> float:
        return round(self.budget - self.spoken, 3)


@dataclass
class Track:
    """A film's complete description track."""

    film: str
    duration: float
    lines: list[Line] = field(default_factory=list)
    generator: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)

    def words(self) -> int:
        return sum(len(line.text.split()) for line in self.lines)

    def speaking_seconds(self) -> float:
        return round(sum(line.spoken for line in self.lines), 2)

    def to_dict(self) -> dict:
        return {
            "film": self.film,
            "duration": round(self.duration, 3),
            "generator": self.generator,
            "stats": self.stats,
            "lines": [asdict(line) for line in self.lines],
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")

    @classmethod
    def load(cls, path: str) -> "Track":
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        known = set(Line.__dataclass_fields__)
        return cls(
            film=data.get("film", ""),
            duration=float(data.get("duration", 0)),
            lines=[Line(**{k: v for k, v in item.items() if k in known})
                   for item in data.get("lines", [])],
            generator=data.get("generator", {}),
            stats=data.get("stats", {}),
        )

    def to_vtt(self) -> str:
        """The same track as WebVTT, for tools that already speak subtitles.

        The cue end is the end of the slot, not the end of the speech: a
        player that reads this as a subtitle file should show the line for
        as long as the description owns the silence.
        """
        out = ["WEBVTT", ""]
        for index, line in enumerate(self.lines, start=1):
            out += [str(index),
                    f"{_stamp(line.start)} --> {_stamp(line.start + line.budget)}",
                    line.text, ""]
        return "\n".join(out)


def _stamp(seconds: float) -> str:
    hours, rest = divmod(max(0.0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"

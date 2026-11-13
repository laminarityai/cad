"""The parts of the landing capture that need no browser, no server and no model.

`landing_capture.py` drives the product and writes the page's pictures. This module holds what it
decides without them: what a model session costs, whether a capture shows something it must not,
which stretches of a long recording make the short loop, and the files the page reads.
"""

import json
import re
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ALLOWED_EMAIL: Final = "demo@example.com"
EMAIL: Final = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LOCAL_PATH: Final = re.compile(r"/(?:Users|home|private|var/folders|tmp)/[^\s\"'<>)]+")
USAGE: Final = re.compile(
    r"model usage: input (\d+), cache read (\d+), cache write (\d+), output (\d+)"
)
BUDGET_BYTES: Final = 1_500_000

# USD per million tokens: input, cache read, cache write, output. These are the highest list prices
# of the models the server may run, so the estimate never reads low.
PRICES: Final = (3.0, 0.30, 3.75, 15.0)


def cost(lines: Sequence[str], prices: tuple[float, float, float, float] = PRICES) -> float:
    """What the model usage lines in `lines` cost, in USD."""
    total = 0.0
    for line in lines:
        found = USAGE.search(line)
        if found:
            total += sum(int(n) * p for n, p in zip(found.groups(), prices, strict=True)) / 1e6
    return total


def leaks(text: str, home: str = "") -> list[str]:
    """Everything in `text` a public picture must not show: an email address, a local path."""
    found = [one for one in EMAIL.findall(text) if one != ALLOWED_EMAIL]
    found += LOCAL_PATH.findall(text)
    if home and home in text:
        found.append(home)
    return found


@dataclass(frozen=True, slots=True)
class Cut:
    """A stretch of a recording, in seconds, shown `speed` times as fast."""

    start: float
    end: float
    speed: float = 1.0

    @property
    def shown(self) -> float:
        return (self.end - self.start) / self.speed


def plan(marks: Mapping[str, float], length: float, longest: float = 12.0) -> list[Cut]:
    """The cuts of one recording that make the hero loop.

    `marks` holds seconds from the start of the recording: `options` (the first option tab shows),
    `drawn` (the viewer has drawn), `lines` (the first check line shows) and `done` (no line is
    still running). The loop opens on the options arriving, holds on the drawn model, then plays the
    checks filling in, sped up to fit `longest` seconds in all.
    """
    start = max(marks["options"] - 1.0, 0.0)
    first = Cut(start, min(start + 3.0, length))
    drawn = Cut(max(marks["drawn"] - 0.5, first.end), min(marks["drawn"] + 1.5, length))
    ends = min(marks["done"] + 2.0, length)
    checks = Cut(max(marks["lines"] - 1.0, drawn.end), ends)
    room = max(longest - first.shown - drawn.shown, 2.0)
    checks = Cut(checks.start, checks.end, max(checks.end - checks.start, 0.1) / room)
    cuts = [first, drawn, checks]
    return [one for one in cuts if one.end > one.start]


def ffmpeg_filter(cuts: Sequence[Cut], width: int, fps: int) -> str:
    """The filter graph that joins the cuts into one video `width` px wide."""
    parts = [
        f"[0:v]trim=start={one.start:.2f}:end={one.end:.2f},setpts=(PTS-STARTPTS)/{one.speed:.3f}[v{n}]"
        for n, one in enumerate(cuts)
    ]
    joined = "".join(f"[v{n}]" for n in range(len(cuts)))
    tail = f"{joined}concat=n={len(cuts)}:v=1:a=0,fps={fps},scale={width}:-2[out]"
    return ";".join([*parts, tail])


def png_size(data: bytes) -> tuple[int, int]:
    """Width and height from a PNG's header."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def write_manifest(folder: Path, sizes: Mapping[str, tuple[int, int]]) -> int:
    """Write manifest.json beside the pictures. Returns the bytes the folder's files weigh."""
    (folder / "manifest.json").write_text(
        json.dumps({name: list(sizes[name]) for name in sorted(sizes)}, indent=2) + "\n"
    )
    return sum(one.stat().st_size for one in folder.iterdir() if one.is_file())


def over_budget(total: int) -> bool:
    return total > BUDGET_BYTES

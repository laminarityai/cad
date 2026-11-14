import itertools
import json
import struct
from pathlib import Path

import landing_media as media
import pytest


def test_cost_adds_each_usage_line() -> None:
    lines = [
        "INFO model usage: input 1000000, cache read 0, cache write 0, output 0",
        "INFO something else",
        "INFO model usage: input 0, cache read 1000000, cache write 1000000, output 1000000",
    ]
    assert media.cost(lines) == pytest.approx(3.0 + 0.30 + 3.75 + 15.0)


def test_cost_of_no_usage_is_zero() -> None:
    assert media.cost(["nothing here"]) == 0


def test_leaks_names_an_email_and_a_path_but_allows_the_placeholder() -> None:
    text = "mail demo@example.com or me@corp.io, file /Users/kevin/x/y and /tmp/a"
    assert media.leaks(text) == ["me@corp.io", "/Users/kevin/x/y", "/tmp/a"]
    assert media.leaks("clean words only") == []


def test_leaks_names_the_home_folder() -> None:
    assert media.leaks("under /scratch/h", home="/scratch/h") == ["/scratch/h"]


def test_plan_makes_three_cuts_that_fit_the_longest_loop() -> None:
    marks = {"options": 20.0, "drawn": 30.0, "lines": 32.0, "done": 120.0}
    cuts = media.plan(marks, length=140.0)
    assert cuts[0].start == 19.0
    assert sum(c.shown for c in cuts) == pytest.approx(12.0)
    assert all(a.end <= b.start for a, b in itertools.pairwise(cuts))


def test_plan_stays_inside_a_short_recording() -> None:
    marks = {"options": 0.2, "drawn": 1.0, "lines": 1.5, "done": 2.0}
    cuts = media.plan(marks, length=3.0)
    assert cuts[0].start == 0
    assert all(c.end <= 3.0 for c in cuts)


def test_filter_joins_every_cut() -> None:
    graph = media.ffmpeg_filter([media.Cut(1, 4), media.Cut(10, 20, 5)], width=800, fps=10)
    assert "[v0]" in graph
    assert "concat=n=2" in graph
    assert "setpts=(PTS-STARTPTS)/5.000" in graph
    assert graph.endswith("scale=800:-2[out]")


def test_png_size_reads_the_header() -> None:
    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 1280, 800)
    assert media.png_size(header) == (1280, 800)
    with pytest.raises(ValueError):
        media.png_size(b"GIF89a" + bytes(30))


def test_manifest_lists_sizes_and_weighs_the_folder(tmp_path: Path) -> None:
    (tmp_path / "a.webp").write_bytes(bytes(100))
    weight = media.write_manifest(tmp_path, {"a.webp": (10, 20)})
    assert json.loads((tmp_path / "manifest.json").read_text()) == {"a.webp": [10, 20]}
    assert weight > 100
    assert not media.over_budget(weight)
    assert media.over_budget(2_000_000)

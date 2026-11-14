"""The files the landing capture writes from what the browser recorded."""

import subprocess
from pathlib import Path
from typing import Final

import landing_media as media

LOOP_WIDTH: Final = 800
LOOP_FPS: Final = 10


def to_webp(source: Path, target: Path, quality: int) -> tuple[int, int]:
    subprocess.run(
        ["cwebp", "-quiet", "-q", str(quality), str(source), "-o", str(target)], check=True
    )
    return media.png_size(source.read_bytes())


def cut(recording: Path, marks: dict[str, float], target: Path, crf: int) -> tuple[int, int]:
    """Join the stretches of `recording` that make the loop into `target`, and write its poster."""
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(recording),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    cuts = media.plan(marks, float(probe.stdout))
    graph = media.ffmpeg_filter(cuts, LOOP_WIDTH, LOOP_FPS)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(recording),
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-an",
            "-c:v",
            "libvpx-vp9",
            "-b:v",
            "0",
            "-crf",
            str(crf),
            "-row-mt",
            "1",
            str(target),
        ],
        check=True,
    )
    size = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(target),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    width, height = (int(one) for one in size.stdout.strip().split(","))
    return width, height


def poster(video: Path, target: Path, work: Path) -> None:
    frame = work / "poster.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-sseof",
            "-1",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame),
        ],
        check=True,
    )
    subprocess.run(["cwebp", "-quiet", "-q", "70", str(frame), "-o", str(target)], check=True)

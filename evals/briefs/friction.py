import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from cad.scorecard.score import SCORECARD

CLOCK_SLACK_S: Final = 5.0


@dataclass(frozen=True, slots=True)
class Pages:
    shown: int
    errors: tuple[str, ...]


def read_pages(log: Path) -> Pages:
    entries: list[dict[str, Any]] = []
    if log.is_file():
        entries = [cast(dict[str, Any], json.loads(line)) for line in log.read_text().splitlines()]
    pages = [one for one in entries if one.get("step") == "page"]
    return Pages(
        shown=len(pages),
        errors=tuple(str(one["error"]) for one in entries if "error" in one),
    )


def minutes_to_first_scorecard(
    briefs_root: Path, variants_root: Path, session_seconds: float
) -> float | None:
    """`session_seconds` is a monotonic clock, which does not count sleep; file times do."""
    started = [path.stat().st_mtime for path in briefs_root.glob("*/*") if path.is_file()]
    stored = [path.stat().st_mtime for path in variants_root.glob(f"*/{SCORECARD}")]
    if not started or not stored:
        return None
    seconds = min(stored) - min(started)
    return None if seconds > session_seconds + CLOCK_SLACK_S else seconds / 60

import os
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

RESULT: Final = "result.json"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Share(Frozen):
    numerator: int
    denominator: int


class Trace(Frozen):
    traced: bool
    cards: int
    judged: int
    awaiting: int
    no_brief: int
    numbers: int
    resolved: int
    untraced: tuple[str, ...]
    agent_measurements: tuple[str, ...]
    strict_pass: Share
    coverage: Share


class Friction(Frozen):
    confirmation_pages: int
    ask_calls: int
    minutes_to_first_scorecard: float | None


class BriefResult(Frozen):
    id: str
    domain: str
    status: Literal["finished", "session_failed"]
    model: str | None
    cost_usd: float | None
    turns: int | None
    seconds: float
    note: str | None
    trace: Trace | None
    friction: Friction


def result_path(out: Path, brief_id: str) -> Path:
    return out / brief_id / RESULT


def is_finished(out: Path, brief_id: str) -> bool:
    path = result_path(out, brief_id)
    return path.is_file() and BriefResult.model_validate_json(path.read_text()).status == "finished"


def write_result(out: Path, result: BriefResult) -> None:
    path = result_path(out, result.id)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json(indent=2) + "\n")
    os.replace(temporary, path)


def read_results(out: Path, ids: list[str]) -> list[BriefResult]:
    paths = [result_path(out, one) for one in ids]
    return [BriefResult.model_validate_json(path.read_text()) for path in paths if path.is_file()]

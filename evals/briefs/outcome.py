import os
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict
from tracking import By, Decided

RESULT: Final = "result.json"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Share(Frozen):
    numerator: int
    denominator: int


class Counted(Frozen):
    """Cards of one origin, those the session was shown or the server's readings after it, and
    the numbers on them."""

    cards: int
    judged: int
    numbers: int
    resolved: int


NONE_COUNTED: Final = Counted(cards=0, judged=0, numbers=0, resolved=0)


class Trace(Frozen):
    """`awaiting` and `no_brief` count over both origins, since a reading can judge a card the
    session was shown. `failed` says the tracer itself raised, so the trace counts nothing."""

    traced: bool
    shown: Counted
    read: Counted
    awaiting: int
    no_brief: int
    untraced: tuple[str, ...]
    agent_measurements: tuple[str, ...]
    strict_pass: Share
    coverage: Share
    agent_coverage: Share = Share(numerator=0, denominator=0)
    described_coverage: Share = Share(numerator=0, denominator=0)
    by: dict[By, Decided] = {}
    uncovered: dict[str, int] = {}
    failed: bool = False


class Friction(Frozen):
    confirmation_pages: int
    ask_calls: int
    minutes_to_first_result: float | None


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

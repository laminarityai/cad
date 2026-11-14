"""What one in-process Auto run did, and whether it did what its brief expects.

A brief's grader may carry an `expect` block:

    expect:
      stop: conflict          # a NeedsPerson reason, or all_pass
      within_builds: 6        # optional: every build under the run counts
      names: [[deflection, stiff], [mass, weigh]]   # optional, live models only

`names` reads the note the agent wrote, so it is judged only for a live model: the scripted agent's
note is fixed text.

A brief with no `expect` passes when its run stops and nothing went wrong on the way.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Literal

from asking import Asking
from pydantic import BaseModel, ConfigDict, ValidationError

from cad.auto.model import Bounds

RESULT: Final = "auto.json"
EVENTS: Final = "events.json"


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Expect(Frozen):
    stop: str | None = None
    within_builds: int | None = None
    names: tuple[tuple[str, ...], ...] = ()

    @staticmethod
    def of(grader: Mapping[str, Any]) -> "Expect":
        return Expect.model_validate(grader.get("expect") or {})


def expect_problems(brief_id: str, grader: Mapping[str, Any]) -> list[str]:
    """What is wrong with a brief's expect block, so a run can refuse it before any session."""
    try:
        Expect.of(grader)
    except ValidationError as error:
        return [
            f"brief {brief_id}: expect.{'.'.join(map(str, one['loc']))}: {one['msg']}"
            for one in error.errors()
        ]
    return []


class AutoResult(Frozen):
    id: str
    domain: str
    model: str
    status: Literal["stopped", "not_stopped", "failed"]
    run_id: str | None
    stop: str | None
    bounds: tuple[Bounds, ...]
    report: str
    builds: int
    stopped_run: str | None
    variants: int
    containers: int
    pages: int
    tool_errors: int
    seconds: float
    problems: tuple[str, ...]
    asking: Asking | None = None

    @property
    def passed(self) -> bool:
        return self.status == "stopped" and not self.problems


def judge(
    expect: Expect,
    live: bool,
    stop: str | None,
    report: str,
    builds: int,
    bounds: tuple[Bounds, ...],
) -> tuple[str, ...]:
    problems: list[str] = []
    if expect.stop is not None and stop != expect.stop:
        problems.append(f"expected the stop {expect.stop}, got {stop}")
    if stop == "conflict" and not bounds:
        problems.append("a conflict stop carried no Bounds")
    if expect.within_builds is not None and builds > expect.within_builds:
        problems.append(f"{builds} builds, more than {expect.within_builds}")
    lowered = report.lower()
    for group in expect.names if live else ():
        if not any(word.lower() in lowered for word in group):
            problems.append(f"the stop's report names none of {', '.join(group)}")
    return tuple(problems)


def write_result(out: Path, result: AutoResult) -> None:
    path = out / result.id / RESULT
    temporary = path.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json(indent=2) + "\n")
    os.replace(temporary, path)


def summary_line(result: AutoResult) -> str:
    verdict = "pass" if result.passed else "FAIL"
    stop = result.stop or result.status
    extra = f"; {'; '.join(result.problems)}" if result.problems else ""
    return (
        f"{result.id}: {verdict}, {stop}, {result.builds} builds, "
        f"{result.variants} variants, {result.seconds:.1f}s{_asked(result.asking)}{extra}"
    )


def _asked(asking: Asking | None) -> str:
    if asking is None:
        return ""
    asked = f"asked {asking.questions}" if asking.asked_before_build else "asked nothing"
    searched = "searched" if asking.searched_before_build else "no search"
    stated = {None: "", True: ", stated brief unasked", False: ", stated brief asked"}
    return f", {asked}, {searched} before the first build{stated[asking.stated_unasked]}"

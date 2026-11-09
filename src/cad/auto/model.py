import hashlib
import re
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cad.briefs.model import MAX_NOTE_CHARS
from cad.projects.model import ProjectId
from cad.variants.entry import VariantRefused

RUN_ID: Final = re.compile(r"^((?:p|pb)-[0-9a-f]{16})-r[0-9a-f]{16}$")


class RunRefused(VariantRefused):
    pass


class UnknownRun(RunRefused):
    pass


class TamperedRun(RunRefused):
    pass


def nth_run_id(project: ProjectId, brief_id: str, number: int) -> str:
    # Derived, not random: two concurrent starts of a brief name the same run, so one wins.
    digest = hashlib.sha256(f"{brief_id}/{number}".encode()).hexdigest()
    return f"{project}-r{digest[:16]}"


def run_project(run_id: str) -> ProjectId:
    match = RUN_ID.fullmatch(run_id)
    if match is None:
        raise UnknownRun(
            f"a run id is a project id, -r and 16 lowercase hex digits, not {run_id!r}"
        )
    return ProjectId(match.group(1))


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Mark(StrEnum):
    PASS = "pass"
    PASS_RESEARCHED = "pass_researched"
    FAIL = "fail"
    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    AWAITS_PERSON = "awaits_person"


class Standing(_Frozen):
    revision: Annotated[int, Field(ge=1)]
    variant_id: str
    code_sha256: str
    built: bool
    marks: tuple[tuple[str, Mark], ...]


class Read(_Frozen):
    material_key: str
    field: Literal["density"]
    value: str
    basis: Literal["table", "researched"]


class Bounds(_Frozen):
    quantity: Literal["mass", "volume"]
    statement: str
    requirements: tuple[str, ...]
    reads: tuple[Read, ...] = ()


class AllPass(_Frozen):
    kind: Literal["all_pass"] = "all_pass"
    researched: tuple[str, ...]
    unverified: tuple[str, ...]


class NeedsPerson(_Frozen):
    kind: Literal["needs_person"] = "needs_person"
    why: Literal["conflict", "proposes_requirements", "source_to_confirm", "agent_asked"]
    requirements: tuple[str, ...] = ()
    bounds: tuple[Bounds, ...] = ()
    note: str = ""

    @model_validator(mode="after")
    def _holds_what_its_reason_needs(self) -> Self:
        if bool(self.bounds) != (self.why == "conflict"):
            raise ValueError("bounds are set exactly when the reason is a conflict")
        if bool(self.note) != (self.why == "agent_asked"):
            raise ValueError("note is set exactly when the agent asked")
        return self


class AccountLimit(_Frozen):
    kind: Literal["account_limit"] = "account_limit"
    refused: str | None
    reason: str


type StopReason = Annotated[AllPass | NeedsPerson | AccountLimit, Field(discriminator="kind")]


class Started(_Frozen):
    kind: Literal["started"] = "started"
    brief_id: str
    project: str
    decision_sha256: str
    material_key: str
    watermark: tuple[tuple[str, int], ...]
    conflicts: tuple[Bounds, ...]


class Revised(_Frozen):
    kind: Literal["revised"] = "revised"
    standing: Standing


class Proposed(_Frozen):
    kind: Literal["proposed"] = "proposed"
    requirements: tuple[str, ...]


class Asked(_Frozen):
    kind: Literal["asked"] = "asked"
    note: Annotated[str, Field(min_length=1, max_length=MAX_NOTE_CHARS)]


class Capped(_Frozen):
    kind: Literal["capped"] = "capped"
    refused: str | None
    reason: str


type Event = Annotated[Started | Revised | Proposed | Asked | Capped, Field(discriminator="kind")]


class Running(_Frozen):
    kind: Literal["running"] = "running"
    start: Started
    history: tuple[Standing, ...] = ()

    @property
    def failing(self) -> tuple[str, ...]:
        if not self.history:
            return ()
        marks = self.history[-1].marks
        return tuple(rid for rid, mark in marks if mark in (Mark.FAIL, Mark.UNKNOWN))


class Stopped(_Frozen):
    kind: Literal["stopped"] = "stopped"
    start: Started
    history: tuple[Standing, ...]
    reason: StopReason
    report: str


type AutoState = Annotated[Running | Stopped, Field(discriminator="kind")]


class Unsettled(_Frozen):
    pass


class AutoRun(_Frozen):
    run_id: str
    state: AutoState
    settling: bool = False


class RunStopped(RunRefused):
    def __init__(self, run: AutoRun) -> None:
        assert isinstance(run.state, Stopped)
        super().__init__(
            f"auto run {run.run_id} has stopped, so nothing more is built or scored under it. "
            f"{run.state.report}"
        )
        self.run = run

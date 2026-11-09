from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cad.checks.result import (
    CheckResult,
    Comparator,
    Measured,
    Read,
    ReadResearched,
    Step,
    Verdict,
)
from cad.scorecard.waiting import Waiting
from cad.tables.materials import Source


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Comparison(_Frozen):
    """One measure of the deciding check, held to one confirmed quantity.

    The measured value is the measure called `measure` on the result of `Checked.check_id` in
    `Scorecard.results`, so it exists once on the card. `limit` is the value the person confirmed.
    """

    measure: str
    comparator: Comparator
    limit: Measured
    verdict: Verdict


class Checked(_Frozen):
    """A requirement that a check in the suite decides. It is unknown when that check could not
    measure, and it is still covered.

    `basis` is `researched` when the deciding result read a researched value, and `researched`
    names each one with its source and quote (ADR-0009). Report such a pass as "passes on
    researched data", never as a plain pass."""

    kind: Literal["checked"] = "checked"
    requirement_id: str
    statement: str
    check_id: str
    verdict: Verdict
    reason: str
    comparisons: tuple[Comparison, ...]
    basis: Literal["checks", "researched"] = "checks"
    researched: tuple[ReadResearched, ...] = Field(default=(), exclude_if=lambda one: not one)

    @model_validator(mode="after")
    def _basis_names_the_research(self) -> Self:
        if (self.basis == "researched") != bool(self.researched):
            raise ValueError("basis is researched exactly when researched names a value")
        return self


class Unverified(_Frozen):
    """A requirement that no reviewed check covers. It has no verdict."""

    kind: Literal["unverified"] = "unverified"
    requirement_id: str
    statement: str


type RequirementResult = Annotated[Checked | Unverified | Waiting, Field(discriminator="kind")]


class AgainstBrief(_Frozen):
    """The variant was scored against the requirements a person confirmed, in the order they
    saw them. `decision_sha256` names the signed decision, which pins the brief and the
    requirements."""

    kind: Literal["against_brief"] = "against_brief"
    brief_id: str
    decision_sha256: str
    requirements: tuple[RequirementResult, ...]
    unverified_requirements: tuple[str, ...]

    @model_validator(mode="after")
    def _lists_the_unverified_entries(self) -> Self:
        ids = tuple(one.requirement_id for one in self.requirements if isinstance(one, Unverified))
        if ids != self.unverified_requirements:
            raise ValueError("unverified_requirements must list the Unverified requirements")
        return self


class NoBrief(_Frozen):
    """Scored with no brief: the card covers the universal checks and no requirement."""

    kind: Literal["no_brief"] = "no_brief"


class AwaitingConfirmation(_Frozen):
    """Scored against a brief whose requirements nobody has confirmed yet, so none is judged."""

    kind: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    brief_id: str


type Basis = Annotated[NoBrief | AwaitingConfirmation | AgainstBrief, Field(discriminator="kind")]


class PendingCheck(_Frozen):
    """A check whose background job has not finished. It has no verdict and no number yet: score
    the variant again to see its result."""

    kind: Literal["pending"] = "pending"
    check_id: str
    formula: str
    sources: tuple[Source, ...]
    version: str
    instance: str = Field(default="", exclude_if=lambda instance: not instance)
    reads: tuple[Read, ...] = Field(default=(), exclude_if=lambda reads: not reads)


AGENT_MEASUREMENT: Final = "agent's own measurement, not verified"


class AgentValue(_Frozen):
    """One number the agent's own code reported. It is not a check `Measure`, so nothing written
    for check results accepts it."""

    name: str
    value: Measured


class AgentMeasurement(_Frozen):
    """Information only: what the agent's own measuring code reported for an unchecked
    requirement. It has no verdict, limit or comparator, its requirement stays unverified, and
    nothing graded may read it. `failed` says why the code gave no values."""

    kind: Literal["agent_measurement"] = "agent_measurement"
    label: Literal["agent's own measurement, not verified"] = AGENT_MEASUREMENT
    requirement_id: str
    title: str
    code_sha256: str
    code: str
    values: tuple[AgentValue, ...]
    failed: str | None
    note: str | None = Field(default=None, exclude_if=lambda note: note is None)


class Scorecard(BaseModel):
    """All of a variant's check results, each with its formula and source.

    `brep_sha256` names the shape the checks measured. `step` names the STEP derived from it, or
    says why there is none. `table_version` and `check_image_digest` name the materials table
    and the analysis image that the checks ran in. Each result carries its own check version.
    `basis` says what the card was scored against, and holds the requirements when there are any.
    `pending` names the checks whose results are not in yet.
    `not_verified` holds the agent's own measurements, which are information and never a verdict.
    `rebuilt_from` names the variant an earlier sandbox stored, when the checks scored its stored
    code rebuilt as `variant_id`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str
    rebuilt_from: str | None = None
    material_key: str
    table_version: str
    check_image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult | PendingCheck, ...]
    pending: tuple[str, ...] = ()
    basis: Basis
    not_verified: tuple[AgentMeasurement, ...] = Field(default=(), exclude_if=lambda rows: not rows)

    @property
    def finished(self) -> tuple[CheckResult, ...]:
        return tuple(one for one in self.results if isinstance(one, CheckResult))

    @model_validator(mode="after")
    def _lists_the_pending_checks(self) -> Self:
        ids = tuple(one.check_id for one in self.results if isinstance(one, PendingCheck))
        if ids != self.pending:
            raise ValueError("pending must list the PendingCheck results")
        return self

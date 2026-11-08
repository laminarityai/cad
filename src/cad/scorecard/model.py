from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from cad.checks.result import CheckResult, Comparator, Measured, Step, Verdict

NO_REQUIREMENTS_NOTE = (
    "Phase 1 reads no requirements from the brief, so unverified_requirements is empty. "
    "This scorecard covers only the universal checks above and says nothing about whether the "
    "variant meets the brief."
)


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
    measure, and it is still covered."""

    kind: Literal["checked"] = "checked"
    requirement_id: str
    statement: str
    check_id: str
    verdict: Verdict
    reason: str
    comparisons: tuple[Comparison, ...]


class Unverified(_Frozen):
    """A requirement that no reviewed check covers. It has no verdict."""

    kind: Literal["unverified"] = "unverified"
    requirement_id: str
    statement: str


type RequirementResult = Annotated[Checked | Unverified, Field(discriminator="kind")]


class AgainstBrief(_Frozen):
    """The variant was scored against the requirements a person confirmed, in the order they
    saw them. `decision_sha256` names the signed decision, which pins the brief and the
    requirements."""

    kind: Literal["against_brief"] = "against_brief"
    brief_id: str
    decision_sha256: str
    requirements: tuple[RequirementResult, ...]
    unverified_requirements: tuple[str, ...]


class Scorecard(BaseModel):
    """All of a variant's check results, each with its formula and source.

    `brep_sha256` names the shape the checks measured. `step` names the STEP derived from it, or
    says why there is none. `table_version` and `image_digest` name the materials table and the
    sandbox image that the run used. Each result carries its own check version.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str
    material_key: str
    table_version: str
    image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult, ...]
    unverified_requirements: tuple[str, ...] = ()
    requirements_note: str = NO_REQUIREMENTS_NOTE

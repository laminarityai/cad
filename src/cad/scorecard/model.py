from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cad.checks.result import CheckResult, Comparator, Measured, Step, Verdict


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


class Scorecard(BaseModel):
    """All of a variant's check results, each with its formula and source.

    `brep_sha256` names the shape the checks measured. `step` names the STEP derived from it, or
    says why there is none. `table_version` and `image_digest` name the materials table and the
    sandbox image that the run used. Each result carries its own check version. `basis` says
    what the card was scored against, and holds the requirements when there are any.
    `rebuilt_from` names the variant an earlier sandbox stored, when the checks scored its stored
    code rebuilt as `variant_id`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str
    rebuilt_from: str | None = None
    material_key: str
    table_version: str
    image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult, ...]
    basis: Basis

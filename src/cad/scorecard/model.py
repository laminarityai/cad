from typing import Annotated, Final, Literal, Self

from pydantic import Field, model_validator

from cad.checks.result import (
    BodyMaterial,
    CheckResult,
    Comparator,
    Materials,
    Measured,
    Read,
    ReadResearched,
    Step,
    Verdict,
    made_of_problem,
)
from cad.frozen import Frozen
from cad.sandbox.bodies import Bodies, bodies_sha256
from cad.scorecard.waiting import Waiting
from cad.tables.materials import Source


class Comparison(Frozen):
    """One measure of the deciding check, held to one confirmed quantity.

    The measured value is the measure called `measure` on the result of `Checked.check_id` in
    `Scorecard.results`, so it exists once on the card. `limit` is the value the person confirmed.
    """

    measure: str
    comparator: Comparator
    limit: Measured
    verdict: Verdict


class Checked(Frozen):
    """A requirement that a check in the suite decides. It is unknown when that check could not
    measure, and it is still covered.

    `basis` is `researched` when the deciding result read a researched value, and `researched`
    names each one with its source and quote (ADR-0009). Report such a pass as "passes on
    researched data", never as a plain pass.

    `instance` names the result of `check_id` that decided it, as `CheckResult.instance` does: the
    load case's id for a stress requirement. That result's `where` names the faces the check fixed
    and loaded.

    `load_case` is `described` when the requirement's load case uses a term beyond the reviewed
    phrases, which the agent combined and the person confirmed (ADR-0007). Report a pass on one
    as "passes on a load case I described", never as a plain pass."""

    kind: Literal["checked"] = "checked"
    requirement_id: str
    statement: str
    check_id: str
    verdict: Verdict
    reason: str
    comparisons: tuple[Comparison, ...]
    instance: str = Field(default="", exclude_if=lambda instance: not instance)
    basis: Literal["checks", "researched"] = "checks"
    researched: tuple[ReadResearched, ...] = Field(default=(), exclude_if=lambda one: not one)
    load_case: Literal["described"] | None = Field(default=None, exclude_if=lambda one: one is None)
    waits_on: Literal["context_part"] | None = Field(
        default=None, exclude_if=lambda one: one is None
    )
    """`context_part` when the requirement is unknown because its context part waits on the
    person to confirm it, so the fit check did not measure against it."""

    @model_validator(mode="after")
    def _basis_names_the_research(self) -> Self:
        if (self.basis == "researched") != bool(self.researched):
            raise ValueError("basis is researched exactly when researched names a value")
        if self.waits_on is not None and self.verdict is not Verdict.UNKNOWN:
            raise ValueError("only an unknown requirement waits on a context part")
        return self


class Unverified(Frozen):
    """A requirement that no reviewed check covers. It has no verdict."""

    kind: Literal["unverified"] = "unverified"
    requirement_id: str
    statement: str


AGENT_CHECK: Final = "agent-written check you approved, not reviewed by our team"


class AgentCheckValue(Frozen):
    """One value an agent-written check's formula read: `read` names where it came from, such as
    geometry:h, team:mass:volume, material:elastic_modulus or source:k."""

    name: str
    read: str
    value: Measured


class AgentChecked(Frozen):
    """A requirement an agent-written check decided: the agent wrote the check before any variant
    of its brief existed, the server gated and froze it, and the person approved it, but our team
    has not reviewed it (ADR-0011). Report its verdict with its label, never as a plain pass. It
    is counted apart from what reviewed checks decide. `value` is the formula's result, None when
    the check could not measure; `reason` says why."""

    kind: Literal["agent_checked"] = "agent_checked"
    label: Literal["agent-written check you approved, not reviewed by our team"] = AGENT_CHECK
    requirement_id: str
    statement: str
    check_sha256: str
    title: str
    formula: str
    version: str
    verdict: Verdict
    reason: str
    value: Measured | None
    comparator: Comparator
    limit: Measured
    inputs: tuple[AgentCheckValue, ...]
    pages: tuple[str, ...]


type RequirementResult = Annotated[
    Checked | Unverified | Waiting | AgentChecked, Field(discriminator="kind")
]


class AgainstBrief(Frozen):
    """The variant was scored against the requirements a person confirmed, in the order they
    saw them. `decision_sha256` names the signed decision, which pins the brief and the
    requirements. `agent_checked_requirements` lists the ones an agent-written check decided,
    which count apart from what reviewed checks cover."""

    kind: Literal["against_brief"] = "against_brief"
    brief_id: str
    decision_sha256: str
    requirements: tuple[RequirementResult, ...]
    unverified_requirements: tuple[str, ...]
    agent_checked_requirements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _lists_the_unverified_entries(self) -> Self:
        ids = tuple(one.requirement_id for one in self.requirements if isinstance(one, Unverified))
        if ids != self.unverified_requirements:
            raise ValueError("unverified_requirements must list the Unverified requirements")
        agent = tuple(
            one.requirement_id for one in self.requirements if isinstance(one, AgentChecked)
        )
        if agent != self.agent_checked_requirements:
            raise ValueError("agent_checked_requirements must list the AgentChecked requirements")
        return self


class NoBrief(Frozen):
    """Scored with no brief: the card covers the universal checks and no requirement."""

    kind: Literal["no_brief"] = "no_brief"


class AwaitingConfirmation(Frozen):
    """Scored against a brief whose requirements nobody has confirmed yet, so none is judged."""

    kind: Literal["awaiting_confirmation"] = "awaiting_confirmation"
    brief_id: str


type Basis = Annotated[NoBrief | AwaitingConfirmation | AgainstBrief, Field(discriminator="kind")]


class PendingCheck(Frozen):
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


class AgentValue(Frozen):
    """One number the agent's own code reported. It is not a check `Measure`, so nothing written
    for check results accepts it."""

    name: str
    value: Measured


class AgentMeasurement(Frozen):
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


JOINTS: Final = "How the bodies are joined is not checked."


class Scorecard(Frozen):
    """All of a variant's check results, each with its formula and source.

    `brep_sha256` names the shape the checks measured. `step` names the STEP derived from it, or
    says why there is none. `table_version` and `check_image_digest` name the materials table
    and the analysis image that the checks ran in. Each result carries its own check version.
    `basis` says what the card was scored against, and holds the requirements when there are any.
    `pending` names the checks whose results are not in yet.
    `not_verified` holds the agent's own measurements, which are information and never a verdict.
    `rebuilt_from` names the variant an earlier sandbox stored, when the checks scored its stored
    code rebuilt as `variant_id`.
    A variant of named bodies has `bodies`, hashed as `bodies_sha256`, and `materials`, one per
    body, in place of `material_key`. `untested` then says what no check covers on any such card.
    """

    variant_id: str
    rebuilt_from: str | None = None
    material_key: str | None = Field(default=None, exclude_if=lambda key: key is None)
    table_version: str
    check_image_digest: str
    brep_sha256: str
    step: Step
    results: tuple[CheckResult | PendingCheck, ...]
    pending: tuple[str, ...] = ()
    basis: Basis
    not_verified: tuple[AgentMeasurement, ...] = Field(default=(), exclude_if=lambda rows: not rows)
    materials: tuple[BodyMaterial, ...] = Field(default=(), exclude_if=lambda each: not each)
    bodies: Bodies = Field(default=(), exclude_if=lambda each: not each)
    bodies_sha256: str | None = Field(default=None, exclude_if=lambda sha256: sha256 is None)
    untested: tuple[str, ...] = Field(default=(), exclude_if=lambda lines: not lines)

    @property
    def finished(self) -> tuple[CheckResult, ...]:
        return tuple(one for one in self.results if isinstance(one, CheckResult))

    @model_validator(mode="after")
    def _names_each_body(self) -> Self:
        problem = made_of_problem(self.material_key, self.materials, self.bodies_sha256)
        if problem is not None:
            raise ValueError(problem)
        if [one.body for one in self.materials] != [body.name for body in self.bodies]:
            raise ValueError("materials must name the bodies in order")
        if self.bodies_sha256 != bodies_sha256(self.bodies):
            raise ValueError("bodies_sha256 must hash the bodies")
        if self.untested != ((JOINTS,) if self.bodies else ()):
            raise ValueError("a card of named bodies says that their joints are not checked")
        return self

    @property
    def scored_with(self) -> Materials:
        return self.materials or str(self.material_key)

    @model_validator(mode="after")
    def _lists_the_pending_checks(self) -> Self:
        ids = tuple(one.check_id for one in self.results if isinstance(one, PendingCheck))
        if ids != self.pending:
            raise ValueError("pending must list the PendingCheck results")
        return self

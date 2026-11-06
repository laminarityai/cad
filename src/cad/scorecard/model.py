from pydantic import BaseModel, ConfigDict

from cad.checks.result import CheckResult

NO_REQUIREMENTS_NOTE = (
    "Phase 1 reads no requirements from the brief, so unverified_requirements is empty. "
    "This scorecard covers only the universal checks above and says nothing about whether the "
    "variant meets the brief."
)


class Scorecard(BaseModel):
    """All of a variant's check results, each with its formula and source.

    `brep_sha256` and `step_sha256` name the shape the checks measured and the STEP derived from
    it. `table_version` and `image_digest` name the materials table and the sandbox image that the
    run used. Each result carries its own check version.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    variant_id: str
    material_key: str
    table_version: str
    image_digest: str
    brep_sha256: str
    step_sha256: str | None
    results: tuple[CheckResult, ...]
    unverified_requirements: tuple[str, ...] = ()
    requirements_note: str = NO_REQUIREMENTS_NOTE

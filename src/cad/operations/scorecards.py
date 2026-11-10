from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import Field

from cad.agent_measurements import run as own
from cad.auto.gate import gate, stops_at_the_limit
from cad.briefs import store as briefs
from cad.briefs.store import ConfirmedSet
from cad.checks import jobs
from cad.context_parts.ids import ContextPartId
from cad.context_parts.store import confirmed_parts, part_brep
from cad.operations.guidance import NOT_VERIFIED, RULE
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.research import brief_table, with_research
from cad.records.roots import Roots
from cad.research.overlay import ProjectTable
from cad.scorecard import material, requirements, score
from cad.tables.materials import KEY_PATTERN

MAX_KEY_CHARS: Final = 64
type MaterialKey = Annotated[
    str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_KEY_CHARS)
]

OWN_MEASUREMENTS = (
    "For a confirmed requirement of kind unchecked, you may pass own_measurements: up to "
    f"{own.MAX_SNIPPETS} entries, each a requirement_id, a short title and build123d Python code "
    f"of at most {own.MAX_CODE_CHARS // 1024} KiB. The code sees `part`, the scored shape, and "
    "calls report(name, value, unit) with a name of lowercase letters, digits and underscores, "
    f"a finite number and a unit of {', '.join(own.UNIT_NAMES)}. It runs in the build sandbox "
    f"after the checks, all entries in one run of at most {own.WALL_SECONDS} seconds. Each entry "
    'becomes a not_verified row labelled "agent\'s own measurement, not verified": its values, '
    "or failed with the reason. The row has no verdict, its requirement stays in "
    "unverified_requirements, and no check or requirement reads it. own_measurements without a "
    "confirmed brief, or naming a requirement a check decides, is refused and nothing is scored. "
)
SCORE_VARIANT = (
    "Score one built variant with the fixed checks closed_solid, interference, mass and "
    "extents (the axis-aligned bounding box in mm). "
    "Each load case of a confirmed min_safety_factor or max_deflection requirement also runs "
    "the fea check, in the background, once per load case: its result carries the load case "
    "id as instance. Until it finishes, the card lists it under pending, the result is a "
    "pending entry with no verdict, and each requirement it decides is waiting. A scorecard "
    "with pending checks is not finished: do not state a pending check's result, and call "
    "score_variant again with the same arguments to wait for it. fea states its error: a "
    "measure within that error of a confirmed limit leaves the requirement unknown. "
    "With a brief_id, each context part confirmed in the brief's project also runs the fit "
    "check in the background, against the variant as built, so build it in the part's frame. "
    "Its result carries the part_id as instance and measures overlap_volume and "
    "min_clearance: it fails when the variant overlaps the part, and it decides each "
    "min_clearance and max_clearance requirement on that part. A clearance requirement whose "
    "part is not confirmed is unknown. Without brief_id no fit runs. "
    "When an earlier version of the sandbox stored the variant, score_variant rebuilds its "
    "stored code first and scores the new variant: the scorecard's variant_id is the new id, "
    "and rebuilt_from is the id you passed. It rebuilds even when the earlier build failed, "
    "because the new sandbox may build it. A rebuild that does not build is an error that "
    "gives the build outcome. "
    "Every result has a verdict (pass, fail or unknown), "
    "its measured values, its formula, its sources and its check version. unknown means the "
    "check could not decide, and it is not a pass. "
    "Each result's reads say, for each material value the check takes, whether the table "
    "cites it, the project researched it (with the url and quote), or the table lacks it. "
    "When a check read a missing material value, the card's research holds a request for it: "
    "answer it with submit_research and score again. A result or requirement whose basis is "
    'researched rests on a researched value: report its pass as "passes on researched data", '
    "naming the field, url and quote. Missing geometry is never researched. "
    "Pass brief_id when the user has a brief. Once the user has confirmed its requirements, the "
    "scorecard's basis is against_brief: for each confirmed requirement it names the check that "
    "decided it, a verdict, and each limit the user confirmed, and unverified_requirements lists "
    "every requirement that no reviewed check covers. The measured value for a limit is the "
    "measure of the same name in that check's result. Before the user confirms, the basis is "
    "awaiting_confirmation and no requirement is judged. Without brief_id the basis is no_brief "
    "and the scorecard covers no requirement. A limit counts as met up to one part in a billion, "
    "an allowance for float noise in unit conversion and not an engineering tolerance. envelope "
    "compares the bounding box of the part as built, never rotated, so it is pass or unknown and "
    "never fail. When you report the scorecard, give every verdict as it states it, with each "
    "check's formula and source, the table version and the basis, and say that every "
    "requirement it did not judge was not checked. "
    "material_key names the material: a key from list_materials when the table lists that same "
    "material, and otherwise a key of your own that names it. A key the table lacks is scored "
    "as the project's own row, project- and your key, and the card's research asks for each "
    "value a check read. When the user confirmed a made_of requirement for the brief, pass "
    "that key: any other material_key is refused and nothing is scored. "
    "The card's material says which key was used and what set it, the confirmed requirement or "
    "your argument. When your argument set it, say so wherever a result rests on the material. "
    "You cannot change a check or the materials table. "
    "Only score_variant runs a check. "
    "Scoring the same variant and key again gives the same scorecard while the materials table, "
    "the sandbox image and the confirmed requirements are unchanged. Scoring a rebuilt "
    "variant by its new id gives the same scorecard with rebuilt_from empty. "
    "In Test mode, score only the variant the user picked. "
    "Under an Auto run, which the conversation holds, pass the run's brief_id: once the run has "
    "stopped, the scorecard is refused before any check runs, and a check the account's usage "
    "limit refuses stops the run. " + OWN_MEASUREMENTS + RULE + " " + NOT_VERIFIED
)

SCORECARD = (
    "Read the scorecard of a variant that score_variant already ran, from the stored results of "
    "its checks. It starts no check, builds nothing and waits for nothing: a check that has not "
    "finished is listed under pending, and a variant that was never scored for this material is "
    "an error. Pass the same variant_id, material_key and brief_id as the score_variant call. "
    "It has the same fields as the score_variant result, except that it never holds the agent's "
    "own measurements, which only the score_variant call that ran them returns. "
    + RULE
    + " "
    + NOT_VERIFIED
)


class ScoreVariantInput(Input):
    variant_id: str
    material_key: MaterialKey
    brief_id: str | None = None
    own_measurements: own.OwnMeasurements | None = None


class ScorecardInput(Input):
    variant_id: str
    material_key: MaterialKey
    brief_id: str | None = None


@dataclass(frozen=True, slots=True)
class Judged:
    confirmed: ConfirmedSet | None
    assess: score.Assess
    demand: jobs.Demand
    table: ProjectTable
    material_key: str


def _context(roots: Roots, brief_id: str) -> dict[ContextPartId, jobs.PartBrep]:
    project = briefs.read_brief(roots, brief_id).project
    return {
        part.record.id: jobs.PartBrep(part.record.brep_sha256, part_brep(roots.projects, part))
        for part in confirmed_parts(roots.projects, project)
    }


def judged(tenant: Tenant, brief_id: str | None, material_key: str) -> Judged:
    confirmed = None
    assess, demand = score.no_brief, score.NO_DEMAND
    if brief_id is not None:
        confirmed = briefs.confirmed_requirements(tenant.roots, brief_id)
        assess = (
            requirements.awaiting(brief_id)
            if confirmed is None
            else requirements.against(confirmed)
        )
        demand = requirements.demand(confirmed, _context(tenant.roots, brief_id))
    table = brief_table(tenant.roots, brief_id)
    key = table.table.row_key(material_key)
    material.refuse_other_material(confirmed, key, table.table)
    return Judged(confirmed, assess, demand, table, key)


def score_variant(tenant: Tenant, arguments: ScoreVariantInput) -> material.ReportedScorecard:
    gate(tenant, arguments.brief_id)
    basis = judged(tenant, arguments.brief_id, arguments.material_key)
    if arguments.own_measurements:
        own.refuse_unless_unchecked(basis.confirmed, arguments.own_measurements)
    with stops_at_the_limit(tenant.roots, tenant.auto_run, arguments.variant_id):
        scored = score.score_variant(
            arguments.variant_id,
            basis.material_key,
            tenant.variants,
            basis.assess,
            demand=basis.demand,
            table=basis.table.table,
        )
    card = with_research(
        material.reported(scored, basis.confirmed), basis.table, arguments.brief_id
    )
    if arguments.own_measurements:
        rows = own.measure(tenant.variants, card.variant_id, arguments.own_measurements)
        card = own.attach(card, rows)
    return card


def scorecard(tenant: Tenant, arguments: ScorecardInput) -> material.ScorecardSnapshot:
    basis = judged(tenant, arguments.brief_id, arguments.material_key)
    peeked = score.peek_variant(
        arguments.variant_id,
        basis.material_key,
        tenant.variants,
        basis.assess,
        demand=basis.demand,
        table=basis.table.table,
    )
    return material.snapshot(
        with_research(material.reported(peeked, basis.confirmed), basis.table, arguments.brief_id)
    )


def names_a_material(tenant: Tenant, arguments: ScorecardInput) -> bool:
    """Whether material_key names a row of the brief's table, or the material the user confirmed,
    so a card nobody scored yet may still come."""
    basis = judged(tenant, arguments.brief_id, arguments.material_key)
    return (
        basis.material_key in basis.table.table.materials
        or material.pinned_by(basis.confirmed) is not None
    )


OPERATIONS: Final = (
    operation(
        name="score_variant",
        audience=Audience.AGENT,
        description=SCORE_VARIANT,
        input=ScoreVariantInput,
        output=material.ReportedScorecard,
        run=score_variant,
    ),
    operation(
        name="scorecard",
        audience=BOTH,
        description=SCORECARD,
        input=ScorecardInput,
        output=material.ScorecardSnapshot,
        run=scorecard,
    ),
)

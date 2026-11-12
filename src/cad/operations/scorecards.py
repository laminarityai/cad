from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Final

from pydantic import Field

from cad.agent_checks import harness, own
from cad.agent_checks.model import MAX_CODE_CHARS, UNITS
from cad.auto.gate import gate, stops_at_the_limit
from cad.briefs import assumptions as assuming
from cad.briefs import store as briefs
from cad.briefs.assumptions import Assumption
from cad.briefs.model import ON_PART, Requirement, Target
from cad.briefs.store import ConfirmedSet
from cad.checks import jobs
from cad.confirmations.requirements import plain_names
from cad.context_parts.ids import ContextPartId
from cad.context_parts.store import fit_targets, part_brep
from cad.operations.agent_checks import with_agent_checks
from cad.operations.guidance import NOT_VERIFIED, RULE
from cad.operations.model import BOTH, Audience, Input, Tenant, operation
from cad.operations.research import brief_table, with_research
from cad.records.roots import Roots
from cad.research.overlay import ProjectTable
from cad.sandbox import image
from cad.scorecard import assumed, awaiting, material, requirements, score, unjudged
from cad.tables.materials import KEY_PATTERN
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MaterialChoice, MaterialMissing

MAX_KEY_CHARS: Final = 64
type MaterialKey = Annotated[
    str, Field(pattern=f"^{KEY_PATTERN.pattern}$", max_length=MAX_KEY_CHARS)
]

OWN_MEASUREMENTS = (
    "For a confirmed requirement of kind unchecked, you may pass own_measurements: up to "
    f"{own.MAX_SNIPPETS} entries, each a requirement_id, a short title and build123d Python code "
    f"of at most {MAX_CODE_CHARS // 1024} KiB. The code sees `part`, the scored shape, and "
    "calls report(name, value, unit) with a name of lowercase letters, digits and underscores, "
    f"a finite number and a unit of {', '.join(UNITS)}. It runs in the build sandbox after "
    f"the checks, all entries in one run of at most {harness.WALL_SECONDS} seconds. Each entry "
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
    "Every result has its measured values, its formula, its sources and its check version, "
    "and a verdict (pass, fail or unknown) unless its kind is measure_only. unknown means the "
    "check could not decide, so no check measured what it covers, and it is not a pass. Wherever "
    "you mention it, in a reply or an auto_ask note, say plainly that no check measured it and "
    "give the check's reason. An estimate of your own never stands in for it. "
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
    "awaiting_confirmation and no requirement is judged. A stated target that waits for the "
    "user's Confirm is listed under awaiting, beside the measure of its deciding check and "
    "with no verdict: report it as waiting for the user, give the measure, and never call it "
    "a pass or a fail. After they confirm, scoring the same variant again judges the same "
    "stored check results against it with no rebuild. A check result for a load case that only "
    "an awaiting or assumed target reads has kind measure_only and no verdict: report its "
    "measures and never call it a pass or a fail. "
    "Without brief_id the basis is no_brief "
    "and the scorecard covers no requirement. A limit counts as met up to one part in a billion, "
    "an allowance for float noise in unit conversion and not an engineering tolerance. envelope "
    "compares the bounding box of the part as built, never rotated, so it is pass or unknown and "
    "never fail. When you report the scorecard, give every verdict as it states it, with each "
    "check's formula and source, the table version and the basis, and say that every "
    "requirement it did not judge was not checked. "
    "The material is the one the person confirmed in a made_of requirement. When none did, it "
    "is the one you chose for the variant's slot with build_variant, so pass the brief_id and "
    "no material_key. material_key overrides that choice for one call: a key from list_materials "
    "when the table lists that same material, and otherwise a key of your own that names it. A "
    "key the table lacks is scored as the project's own row, project- and your key, and the "
    "card's research asks for each value a check read. When the user confirmed a made_of "
    "requirement for the brief, any other material_key is refused and nothing is scored. "
    "The card's material says which key was used and what set it: the confirmed requirement, or "
    "the agent, with the reason you recorded. When the agent set it, say so, and give the "
    "reason, wherever a result rests on the material. "
    "You cannot change a check or the materials table. "
    "Only score_variant runs a check. "
    "Scoring the same variant and key again gives the same scorecard while the materials table, "
    "the sandbox image and the confirmed requirements are unchanged. Scoring a rebuilt "
    "variant by its new id gives the same scorecard with rebuilt_from empty. "
    "When the user asks about one variant they picked, score only that variant. "
    "Under this conversation's Auto run, pass the run's brief_id. After any stop in this "
    "conversation, every score is refused before any check runs until the person writes or "
    "answers. A check the account's usage limit refuses stops the run. "
    + OWN_MEASUREMENTS
    + RULE
    + " "
    + NOT_VERIFIED
)

SCORECARD = (
    "Read the scorecard of a variant that score_variant already ran, from the stored results of "
    "its checks. It starts no check, builds nothing and waits for nothing: a check that has not "
    "finished is listed under pending, and a variant that was never scored for this material is "
    "an error. Pass the same variant_id, brief_id and material_key, if any, as the "
    "score_variant call. "
    "It has the same fields as the score_variant result, except that it never holds the agent's "
    "own measurements, which only the score_variant call that ran them returns. "
    + RULE
    + " "
    + NOT_VERIFIED
)


class ScoreVariantInput(Input):
    variant_id: str
    material_key: MaterialKey | None = None
    brief_id: str | None = None
    own_measurements: own.OwnMeasurements | None = None


class ScorecardInput(Input):
    variant_id: str
    material_key: MaterialKey | None = None
    brief_id: str | None = None


@dataclass(frozen=True, slots=True)
class Judged:
    confirmed: ConfirmedSet | None
    assess: score.Assess
    demand: jobs.Demand
    table: ProjectTable
    material_key: str
    choice: MaterialChoice | None
    assumptions: tuple[Assumption, ...]
    waiting: tuple[Requirement, ...]


def _context(
    roots: Roots, brief_id: str, targets: Sequence[Target]
) -> dict[ContextPartId, jobs.PartBrep]:
    project = briefs.read_brief(roots, brief_id).project
    named = frozenset(one.part for one in targets if isinstance(one, ON_PART))
    return {
        part.record.id: jobs.PartBrep(part.record.brep_sha256, part_brep(roots.projects, part))
        for part in fit_targets(roots.projects, project, brief_id, named)
    }


def _slot_choice(tenant: Tenant, brief_id: str, variant_id: str) -> MaterialChoice | None:
    key = variant_sets.set_key(tenant.roots, brief_id)
    return variant_sets.choice_of(
        tenant.roots.projects, key, variant_id, image.image_tag(image.BUILD)
    )


def _assumed(tenant: Tenant, brief_id: str) -> tuple[Assumption, ...]:
    held = assuming.in_force(tenant.roots, brief_id)
    return () if held is None else held.assumptions


def _waiting(
    tenant: Tenant, brief_id: str, confirmed: ConfirmedSet | None
) -> tuple[Requirement, ...]:
    """The stated targets the person has not confirmed: the newest proposal's rows, less any the
    confirmed set already holds, which are judged."""
    latest = briefs.read_state(tenant.roots, brief_id).latest
    if latest is None or latest.status is not briefs.Status.PROPOSED:
        return ()
    held = () if confirmed is None else [one.target for one in confirmed.requirements]
    return tuple(one for one in latest.requirements if one.target not in held)


def _targets(
    confirmed: ConfirmedSet | None,
    waiting: tuple[Requirement, ...],
    assumed_by_agent: tuple[Assumption, ...],
) -> list[Target]:
    """Every target a card may show a measure for: confirmed, awaiting Confirm, or assumed."""
    held = () if confirmed is None else confirmed.requirements
    return [
        *(one.target for one in held),
        *(one.target for one in waiting),
        *(one.target for one in assumed_by_agent),
    ]


def with_assumptions(
    card: material.ReportedScorecard, tenant: Tenant, basis: Judged, brief_id: str | None
) -> material.ReportedScorecard:
    if brief_id is None or not (basis.assumptions or basis.waiting):
        return card
    names = plain_names(tenant.roots, brief_id)
    loads = unjudged.unconfirmed_loads(
        [*(one.target for one in basis.waiting), *(one.target for one in basis.assumptions)],
        [] if basis.confirmed is None else [one.target for one in basis.confirmed.requirements],
    )
    return card.model_copy(
        update={
            "results": unjudged.without_verdicts(card.results, loads),
            "assumptions": assumed.rows(basis.assumptions, card.results, names),
            "awaiting": awaiting.rows(basis.waiting, card.results, names),
        }
    )


def judged(
    tenant: Tenant, brief_id: str | None, material_key: str | None, variant_id: str | None
) -> Judged:
    """The key a card is scored with: the one passed, else the person's made_of, else the one the
    agent chose for the variant's slot."""
    confirmed = None
    assess, demand = score.no_brief, score.NO_DEMAND
    held = ()
    waiting: tuple[Requirement, ...] = ()
    if brief_id is not None:
        confirmed = briefs.confirmed_requirements(tenant.roots, brief_id)
        assess = (
            requirements.awaiting(brief_id)
            if confirmed is None
            else requirements.against(confirmed, plain_names(tenant.roots, brief_id))
        )
        held = _assumed(tenant, brief_id)
        waiting = _waiting(tenant, brief_id, confirmed)
        targets = _targets(confirmed, waiting, held)
        demand = requirements.demand(targets, _context(tenant.roots, brief_id, targets))
    table = brief_table(tenant.roots, brief_id)
    pinned = material.pinned_key(confirmed, table.table)
    choice = None
    if brief_id is not None and pinned is None and variant_id:
        choice = _slot_choice(tenant, brief_id, variant_id)
    named = None if material_key is None else table.table.row_key(material_key)
    key = named or pinned or (None if choice is None else choice.key)
    if key is None:
        raise MaterialMissing(
            "no material is known for this variant: pass material_key, or pass the brief_id "
            "of a brief whose confirmed made_of names it, or whose variant set records the "
            "material the agent chose for this variant's slot"
        )
    material.refuse_other_material(confirmed, key, table.table)
    return Judged(confirmed, assess, demand, table, key, choice, held, waiting)


def score_variant(tenant: Tenant, arguments: ScoreVariantInput) -> material.ReportedScorecard:
    gate(tenant.roots, tenant.conversations, tenant.bound_run, arguments.brief_id)
    basis = judged(tenant, arguments.brief_id, arguments.material_key, arguments.variant_id)
    if arguments.own_measurements:
        own.refuse_unless_unchecked(basis.confirmed, arguments.own_measurements)
    with stops_at_the_limit(
        tenant.roots, tenant.conversations, tenant.bound_run, arguments.variant_id
    ):
        scored = score.score_variant(
            arguments.variant_id,
            basis.material_key,
            tenant.variants,
            basis.assess,
            demand=basis.demand,
            table=basis.table.table,
        )
    card = with_research(
        material.reported(scored, basis.confirmed, basis.choice), basis.table, arguments.brief_id
    )
    card = with_assumptions(card, tenant, basis, arguments.brief_id)
    card = with_agent_checks(
        card, tenant.roots, tenant.variants, basis.confirmed, basis.table.table, run=True
    )
    if arguments.own_measurements:
        rows = own.measure(tenant.variants, card.variant_id, arguments.own_measurements)
        card = own.attach(card, rows)
    return card


def scorecard(tenant: Tenant, arguments: ScorecardInput) -> material.ScorecardSnapshot:
    basis = judged(tenant, arguments.brief_id, arguments.material_key, arguments.variant_id)
    peeked = score.peek_variant(
        arguments.variant_id,
        basis.material_key,
        tenant.variants,
        basis.assess,
        demand=basis.demand,
        table=basis.table.table,
    )
    reported = material.reported(peeked, basis.confirmed, basis.choice)
    card = with_research(reported, basis.table, arguments.brief_id)
    card = with_assumptions(card, tenant, basis, arguments.brief_id)
    card = with_agent_checks(
        card, tenant.roots, tenant.variants, basis.confirmed, basis.table.table, run=False
    )
    return material.snapshot(card)


def names_a_material(tenant: Tenant, arguments: ScorecardInput) -> bool:
    """Whether the card's material is a row of the brief's table, the one the user confirmed, or
    the one the agent chose for the slot, so a card nobody scored yet may still come."""
    basis = judged(tenant, arguments.brief_id, arguments.material_key, arguments.variant_id)
    return (
        basis.material_key in basis.table.table.materials
        or material.pinned_by(basis.confirmed) is not None
        or (basis.choice is not None and basis.choice.key == basis.material_key)
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

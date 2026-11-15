from collections.abc import Callable
from pathlib import Path
from typing import Final

from cad.checks import jobs
from cad.checks.lanes import LANES, WAIT_SECONDS, Done, Lanes, Pending, Settled
from cad.checks.report import SPECS, CheckSpec, Request, build_request, reads_of, unknown_for_all
from cad.checks.result import CheckResult, Materials, per_body, single_key
from cad.errors import Refused
from cad.sandbox import host, image
from cad.sandbox.bodies import Bodies, bodies_sha256
from cad.scorecard.model import JOINTS, Basis, NoBrief, PendingCheck, Scorecard
from cad.tables.materials import MaterialsTable
from cad.variants import entry, repair
from cad.variants import store as variants

type Results = tuple[CheckResult | PendingCheck, ...]
type Assess = Callable[[Results], Basis]

NO_DEMAND: Final = jobs.Demand()


class BodiesChanged(Refused):
    pass


class PlacedFitTarget(Refused):
    pass


class NotScored(Refused):
    def __init__(self, vid: str) -> None:
        super().__init__(
            f"variant {vid} has no stored check result for this material to read; "
            "score_variant runs the checks"
        )


class ChecksRunning(NotScored):
    """The quick checks run now and have stored no result yet. Read the card again shortly."""

    def __init__(self, vid: str) -> None:
        Refused.__init__(
            self,
            f"variant {vid} has its checks running and no result stored yet; read it again "
            "in a moment",
        )


def no_brief(results: Results) -> Basis:
    del results
    return NoBrief()


type MadeOf = Materials | Callable[[Bodies], Materials]


def score_variant(
    variant_id: str,
    material: MadeOf,
    root: Path = entry.VARIANTS_ROOT,
    assess: Assess = no_brief,
    lanes: Lanes = LANES,
    demand: jobs.Demand = NO_DEMAND,
    table: MaterialsTable | None = None,
    fetch: variants.Fetch = variants.no_parts,
) -> Scorecard:
    held, rebuilt_from = open_or_rebuild(variant_id, root, fetch)
    request, plan = planned(root, held, material, table, demand)
    return scorecard_of(plan, request, lanes.settle(plan, WAIT_SECONDS), assess, rebuilt_from)


def peek_variant(
    variant_id: str,
    material: MadeOf,
    root: Path,
    assess: Assess = no_brief,
    lanes: Lanes = LANES,
    demand: jobs.Demand = NO_DEMAND,
    table: MaterialsTable | None = None,
) -> Scorecard:
    """The card of `score_variant` as the signed results hold it now. Nothing is built, run or
    waited for: a background job with no stored result is pending while it runs or waits, and
    refused once interrupted too often or when nothing runs it, as after a restart or a failed
    run."""
    held = entry.open_entry(root, variant_id, image.image_tag(image.BUILD))
    request, plan = planned(root, held, material, table, demand)
    match lanes.peek(plan):
        case Settled() as settled:
            return scorecard_of(plan, request, settled, assess)
        case Pending():
            raise ChecksRunning(variant_id)
        case None:
            raise NotScored(variant_id)


def planned(
    root: Path,
    held: entry.Entry,
    material: MadeOf,
    table: MaterialsTable | None,
    demand: jobs.Demand,
) -> tuple[Request, jobs.Plan]:
    _refuse_placed_fit_targets(held, demand)
    table = table or host.materials_table()
    made = material(held.bodies) if callable(material) else material
    try:
        request = build_request(made, table, bodies=held.bodies)
    except ValueError as error:
        raise BodiesChanged(_changed(held)) from error
    return request, jobs.plan(root, held, request, table, demand)


def _refuse_placed_fit_targets(held: entry.Entry, demand: jobs.Demand) -> None:
    """The fit check measures a fit target where it was confirmed, so a variant that moved one
    would show it where no check measured it (ADR-0012)."""
    placed = [use.part_id for use in held.parts if use.placements and use.part_id in demand.parts]
    if placed:
        raise PlacedFitTarget(
            f"variant {held.id} places {', '.join(placed)}, which the brief's fit check now "
            "measures where it was confirmed; build it again reading that part without "
            "placing it"
        )


def _changed(held: entry.Entry) -> str:
    if not held.bodies:
        return f"variant {held.id} is one unnamed body: score it with material_key, not materials"
    names = ", ".join(body.name for body in held.bodies)
    return (
        f"variant {held.id} holds the bodies {names}: score it with materials, one entry for "
        "each body, or with none to use the materials its slot records"
    )


def open_or_rebuild(
    variant_id: str, root: Path, fetch: variants.Fetch = variants.no_parts
) -> tuple[entry.Entry, str | None]:
    """Open the current build of `variant_id`, an outdated id going to the build of its code and
    parts. The build opened is healed first, so a damaged shape never stops a score under either
    id."""
    tag = image.image_tag(image.BUILD)
    repair.heal(root, variant_id, tag, fetch)
    try:
        return entry.open_entry(root, variant_id, tag), None
    except entry.OutdatedVariant as outdated:
        current = entry.variant_id(outdated.code, tag, outdated.parts)
        repair.heal(root, current, tag, fetch)
        rebuilt = variants.rebuild(outdated, root, fetch)
        return entry.open_entry(root, rebuilt.variant_id, tag), outdated.id


def scorecard_of(
    plan: jobs.Plan,
    request: Request,
    settled: Settled,
    assess: Assess,
    rebuilt_from: str | None = None,
) -> Scorecard:
    by_check: dict[str, list[CheckResult | PendingCheck]] = {}
    for one in settled.quick.results:
        by_check.setdefault(one.check_id, []).append(one)
    for job, outcome in zip(plan.background, settled.background, strict=True):
        match outcome:
            case Done(result):
                found: Results = result.results
            case Pending():
                found = tuple(_pending(one, job) for one in job.checks)
            case jobs.Refused(reason):
                found = tuple(
                    one.model_copy(update={"instance": job.instance})
                    for one in unknown_for_all(reason, job.checks)
                )
        for one in found:
            by_check.setdefault(one.check_id, []).append(one)
    results = tuple(one for spec in SPECS for one in by_check.get(spec.id, ()))
    return Scorecard(
        rebuilt_from=rebuilt_from,
        variant_id=plan.quick.variant_id,
        material_key=single_key(request.material),
        materials=per_body(request.material),
        bodies=request.bodies,
        bodies_sha256=bodies_sha256(request.bodies),
        untested=(JOINTS,) if request.bodies else (),
        table_version=request.table_version,
        check_image_digest=settled.quick.check_image_digest,
        brep_sha256=plan.quick.brep_sha256,
        step=settled.quick.step,
        results=results,
        pending=tuple(one.check_id for one in results if isinstance(one, PendingCheck)),
        basis=assess(results),
    )


def _pending(spec: CheckSpec, job: jobs.JobSpec) -> PendingCheck:
    return PendingCheck(
        check_id=spec.id,
        formula=spec.formula,
        sources=spec.sources,
        version=spec.version,
        instance=job.instance,
        reads=reads_of(spec, job.request),
    )

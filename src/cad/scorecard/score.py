from collections.abc import Callable
from pathlib import Path
from typing import Final

from cad.checks import jobs
from cad.checks.lanes import LANES, WAIT_SECONDS, Done, Lanes, Pending, Settled
from cad.checks.report import SPECS, CheckSpec, Request, build_request, reads_of, unknown_for_all
from cad.checks.result import CheckResult
from cad.sandbox import host, image
from cad.sandbox.outcome import Built
from cad.scorecard.model import Basis, NoBrief, PendingCheck, Scorecard
from cad.tables.materials import MaterialsTable
from cad.variants import entry
from cad.variants import store as variants

type Results = tuple[CheckResult | PendingCheck, ...]
type Assess = Callable[[Results], Basis]

NO_DEMAND: Final = jobs.Demand()


class NotScored(entry.VariantRefused):
    def __init__(self, vid: str) -> None:
        super().__init__(
            f"variant {vid} has no stored check result for this material to read; "
            "score_variant runs the checks"
        )


def no_brief(results: Results) -> Basis:
    del results
    return NoBrief()


def score_variant(
    variant_id: str,
    material_key: str,
    root: Path = entry.VARIANTS_ROOT,
    assess: Assess = no_brief,
    lanes: Lanes = LANES,
    demand: jobs.Demand = NO_DEMAND,
    table: MaterialsTable | None = None,
) -> Scorecard:
    held, rebuilt_from = open_or_rebuild(variant_id, root)
    request, plan = planned(root, held, material_key, table, demand)
    return scorecard_of(plan, request, lanes.settle(plan, WAIT_SECONDS), assess, rebuilt_from)


def peek_variant(
    variant_id: str,
    material_key: str,
    root: Path,
    assess: Assess = no_brief,
    lanes: Lanes = LANES,
    demand: jobs.Demand = NO_DEMAND,
    table: MaterialsTable | None = None,
) -> Scorecard:
    """The card of `score_variant` as the signed results hold it now. Nothing is built, run or
    waited for: a background job with no stored result is pending, or refused once interrupted
    too often."""
    held = entry.open_entry(root, variant_id, image.image_tag(image.BUILD))
    request, plan = planned(root, held, material_key, table, demand)
    settled = lanes.peek(plan)
    if settled is None:
        raise NotScored(variant_id)
    return scorecard_of(plan, request, settled, assess)


def planned(
    root: Path,
    held: entry.Entry,
    material_key: str,
    table: MaterialsTable | None,
    demand: jobs.Demand,
) -> tuple[Request, jobs.Plan]:
    table = table or host.materials_table()
    request = build_request(material_key, table)
    return request, jobs.plan(root, held, request, table, demand)


def open_or_rebuild(variant_id: str, root: Path) -> tuple[entry.Entry, str | None]:
    tag = image.image_tag(image.BUILD)
    try:
        return entry.open_entry(root, variant_id, tag), None
    except entry.OutdatedVariant as outdated:
        rebuilt = variants.build_variant(outdated.code, root)
        if not isinstance(rebuilt.outcome, Built):
            raise variants.RebuildFailed(outdated.id, rebuilt) from outdated
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
        material_key=request.material_key,
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

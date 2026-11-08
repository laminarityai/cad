import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Final

from cad.checks import jobs
from cad.checks.lanes import LANES, WAIT_SECONDS, Done, Lanes, Pending, Settled
from cad.checks.report import SPECS, CheckSpec, Request, build_request, unknown_for_all
from cad.checks.result import CheckResult
from cad.sandbox import host, image
from cad.sandbox.outcome import Built, SandboxUnavailable
from cad.scorecard.model import Basis, NoBrief, PendingCheck, Scorecard
from cad.variants import entry
from cad.variants import store as variants

SCORECARD: Final = "scorecard.json"

type Results = tuple[CheckResult | PendingCheck, ...]
type Assess = Callable[[Results], Basis]

NO_DEMAND: Final[jobs.Demand] = MappingProxyType({})


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
) -> Scorecard:
    held, rebuilt_from = open_or_rebuild(variant_id, root)
    table = host.materials_table()
    request = build_request(material_key, table)
    plan = jobs.plan(root, held, request, table, demand)
    card = scorecard_of(plan, request, lanes.settle(plan, WAIT_SECONDS), assess, rebuilt_from)
    store(card, root)
    return card


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
                found = tuple(_pending(one, job.instance) for one in job.checks)
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


def _pending(spec: CheckSpec, instance: str) -> PendingCheck:
    return PendingCheck(
        check_id=spec.id,
        formula=spec.formula,
        sources=spec.sources,
        version=spec.version,
        instance=instance,
    )


def store(card: Scorecard, root: Path) -> Path:
    directory = root / card.variant_id
    path = directory / SCORECARD
    temporary = directory / f".scorecard-{secrets.token_hex(8)}"
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise NotADirectoryError(str(directory))
        temporary.write_text(card.model_dump_json(indent=2) + "\n")
        os.replace(temporary, path)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store the scorecard of variant {card.variant_id}", error, path
        ) from error
    finally:
        temporary.unlink(missing_ok=True)
    return path

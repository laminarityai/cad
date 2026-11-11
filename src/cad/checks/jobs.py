import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, NewType

from cad.checks.container import fea, fit
from cad.checks.container.check import Background, Budget, Quick
from cad.checks.container.wire import LoadCaseWire
from cad.checks.report import IMAGE_TAG, QUICK, SPECS, CheckSpec, Request, build_request, parse
from cad.checks.result import CheckResult, Step, StepMissing
from cad.context_parts.ids import ContextPartId
from cad.frozen import Frozen
from cad.sandbox import container, host, image, stage
from cad.sandbox.outcome import SandboxUnavailable
from cad.tables.materials import MaterialsTable
from cad.variants import entry
from cad.variants.entry import Entry

JobKey = NewType("JobKey", str)

FEA: Final = next(spec for spec in SPECS if spec.id == fea.ID)
FIT: Final = next(spec for spec in SPECS if spec.id == fit.ID)


@dataclass(frozen=True, slots=True)
class PartBrep:
    sha256: str
    data: bytes


@dataclass(frozen=True, slots=True)
class Demand:
    """What the background checks measure against: fea once per load case, fit once per
    context part. Each mapping's key is the result's instance."""

    loads: Mapping[str, LoadCaseWire] = field(default_factory=dict[str, LoadCaseWire])
    parts: Mapping[ContextPartId, PartBrep] = field(default_factory=dict[ContextPartId, PartBrep])


NO_STEP = "a background job keeps no STEP; the quick job derives it"


@dataclass(frozen=True, slots=True)
class JobSpec:
    root: Path
    variant_id: str
    brep_sha256: str
    checks: tuple[CheckSpec, ...]
    budget: Budget
    request: Request
    instance: str = ""
    context: PartBrep | None = None

    @property
    def key(self) -> JobKey:
        reads = {
            name: [read.magnitude, dataclasses.asdict(read.source), dataclasses.asdict(read.basis)]
            for name, read in sorted(self.request.reads.items())
        }
        versions = [one.version for one in self.checks]
        context = None if self.context is None else self.context.sha256
        canonical = json.dumps(
            [self.brep_sha256, IMAGE_TAG, versions, self.request.wire, reads, context],
            sort_keys=True,
            default=str,
        ).encode()
        return JobKey(hashlib.sha256(canonical).hexdigest()[:20])


@dataclass(frozen=True, slots=True)
class Plan:
    quick: JobSpec
    background: tuple[JobSpec, ...]


class JobResult(Frozen):
    check_image_digest: str
    step: Step
    results: tuple[CheckResult, ...]
    timed_out: bool = False


def plan(root: Path, held: Entry, request: Request, table: MaterialsTable, demand: Demand) -> Plan:
    quick = JobSpec(root, held.id, held.brep_sha256, QUICK, Quick(), request)
    loads = tuple(
        JobSpec(
            root,
            held.id,
            held.brep_sha256,
            (FEA,),
            FEA.budget,
            build_request(request.material_key, table, (FEA,), (case,)),
            instance,
        )
        for instance, case in sorted(demand.loads.items())
    )
    parts = tuple(
        JobSpec(
            root,
            held.id,
            held.brep_sha256,
            (FIT,),
            FIT.budget,
            build_request(request.material_key, table, (FIT,), context_bytes=len(part.data)),
            instance,
            part,
        )
        for instance, part in sorted(demand.parts.items())
    )
    return Plan(quick=quick, background=(*loads, *parts))


def run_job(spec: JobSpec) -> JobResult:
    match spec.budget:
        case Quick():
            return _run_quick(spec)
        case Background():
            return _run_background(spec, spec.budget)


def _run_quick(spec: JobSpec) -> JobResult:
    run = host.run_request(spec.variant_id, spec.request, spec.root)
    return JobResult(
        check_image_digest=run.check_image_digest,
        step=run.step,
        results=run.results,
        timed_out=run.timed_out,
    )


def _run_background(spec: JobSpec, budget: Background) -> JobResult:
    held = entry.open_entry(spec.root, spec.variant_id, image.image_tag(image.BUILD))
    image_id = image.current_image(IMAGE_TAG)
    try:
        context = b"" if spec.context is None else spec.context.data
        job = host.check_job(held.brep + context, image_id, spec.request, budget.wall_seconds)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot stage the check sources for variant {held.id}", error, stage.STAGE_ROOT
        ) from error
    job = dataclasses.replace(job, memory_mb=budget.memory_mb, tmpfs_mb=budget.tmpfs_mb)
    parsed = parse(container.run(job), spec.request, job)
    own = {one.id for one in spec.checks}
    return JobResult(
        check_image_digest=image_id,
        step=StepMissing(reason=NO_STEP),
        results=tuple(
            one.model_copy(update={"instance": spec.instance})
            for one in parsed.results
            if one.check_id in own
        ),
        timed_out=parsed.timed_out,
    )


@dataclass(frozen=True, slots=True)
class Refused:
    reason: str

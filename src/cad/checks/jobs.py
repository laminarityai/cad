import dataclasses
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NewType, Protocol

from pydantic import BaseModel, ConfigDict

from cad.checks.container.check import Background, Budget, Quick
from cad.checks.container.wire import LoadCaseWire
from cad.checks.report import IMAGE_TAG, QUICK, SPECS, CheckSpec, Request, build_request, parse
from cad.checks.result import CheckResult, Step, StepMissing
from cad.sandbox import container, host, image, stage
from cad.sandbox.outcome import SandboxUnavailable
from cad.tables.materials import MaterialsTable
from cad.variants import entry
from cad.variants.entry import Entry

JobKey = NewType("JobKey", str)

type Demand = Mapping[str, LoadCaseWire]

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

    @property
    def key(self) -> JobKey:
        reads = {
            name: [read.magnitude, dataclasses.asdict(read.source)]
            for name, read in sorted(self.request.reads.items())
        }
        versions = [one.version for one in self.checks]
        canonical = json.dumps(
            [self.brep_sha256, IMAGE_TAG, versions, self.request.wire, reads],
            sort_keys=True,
            default=str,
        ).encode()
        return JobKey(hashlib.sha256(canonical).hexdigest()[:20])


@dataclass(frozen=True, slots=True)
class Plan:
    quick: JobSpec
    background: tuple[JobSpec, ...]


class JobResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    check_image_digest: str
    step: Step
    results: tuple[CheckResult, ...]
    timed_out: bool = False


def plan(root: Path, held: Entry, request: Request, table: MaterialsTable, demand: Demand) -> Plan:
    quick = JobSpec(root, held.id, held.brep_sha256, QUICK, Quick(), request)
    background = tuple(
        JobSpec(
            root,
            held.id,
            held.brep_sha256,
            (spec,),
            spec.budget,
            build_request(request.material_key, table, (spec,), (case,)),
            instance,
        )
        for spec in SPECS
        if isinstance(spec.budget, Background)
        for instance, case in sorted(demand.items())
    )
    return Plan(quick=quick, background=background)


def run_job(spec: JobSpec) -> JobResult:
    match spec.budget:
        case Quick():
            return _run_quick(spec)
        case Background():
            return _run_background(spec, spec.budget)


def _run_quick(spec: JobSpec) -> JobResult:
    run = host.run_checks(spec.variant_id, spec.request.material_key, spec.root)
    if run.table_version != spec.request.table_version:
        raise SandboxUnavailable(
            "the materials table changed while the checks ran; score the variant again"
        )
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
        job = host.check_job(held.brep, image_id, spec.request, budget.wall_seconds)
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
class Admitted:
    pass


@dataclass(frozen=True, slots=True)
class Refused:
    reason: str


class Meter(Protocol):
    def admit(self, job: JobSpec) -> Admitted | Refused: ...


class Unmetered:
    def admit(self, job: JobSpec) -> Admitted | Refused:
        del job
        return Admitted()

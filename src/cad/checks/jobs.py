import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import NewType, Protocol

from pydantic import BaseModel, ConfigDict

from cad.checks.report import IMAGE_TAG, SPECS, CheckSpec, Request
from cad.checks.result import CheckResult, Step
from cad.sandbox import host
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.entry import Entry

JobKey = NewType("JobKey", str)


@dataclass(frozen=True, slots=True)
class Quick:
    pass


@dataclass(frozen=True, slots=True)
class Background:
    wall_seconds: int
    memory_mb: int
    tmpfs_mb: int


type Budget = Quick | Background


@dataclass(frozen=True, slots=True)
class JobSpec:
    root: Path
    variant_id: str
    brep_sha256: str
    checks: tuple[CheckSpec, ...]
    budget: Budget
    request: Request

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


def plan(root: Path, held: Entry, request: Request) -> Plan:
    quick = JobSpec(root, held.id, held.brep_sha256, SPECS, Quick(), request)
    return Plan(quick=quick, background=())


def run_quick(spec: JobSpec) -> JobResult:
    run = host.run_checks(spec.variant_id, spec.request.material_key, spec.root)
    if run.table_version != spec.request.table_version:
        raise SandboxUnavailable(
            "the materials table changed while the checks ran; score the variant again"
        )
    return JobResult(check_image_digest=run.check_image_digest, step=run.step, results=run.results)


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

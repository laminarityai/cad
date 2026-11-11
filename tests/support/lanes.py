import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from cad.checks.jobs import Background, JobResult, JobSpec, Plan, Quick
from cad.checks.report import SPECS, build_request, unknown_for_all
from cad.checks.result import StepMissing
from cad.tables.materials import load_materials

VID = "0123456789abcdef"
QUICK = Quick()
FEA = Background(wall_seconds=600, memory_mb=2048, tmpfs_mb=768)
LONG = 10.0


def job(root: Path, budget: Quick | Background = QUICK, material: str = "prusament-pla") -> JobSpec:
    (root / VID).mkdir(exist_ok=True)
    checks = SPECS if isinstance(budget, Quick) else SPECS[2:3]
    return JobSpec(root, VID, "b" * 64, checks, budget, build_request(material, load_materials()))


def measured(reason: str) -> JobResult:
    return JobResult(
        check_image_digest="sha256:" + "i" * 64,
        step=StepMissing(reason=reason),
        results=unknown_for_all(reason),
    )


def opened() -> threading.Event:
    gate = threading.Event()
    gate.set()
    return gate


def ran(spec: JobSpec, time: int = 1) -> JobResult:
    return measured(f"run {time} of job {spec.key}")


@dataclass
class Lane:
    gate: threading.Event = field(default_factory=opened)
    error: BaseException | None = None
    timeouts: int = 0


@dataclass
class GatedRunner:
    quick: Lane = field(default_factory=Lane)
    background: Lane = field(default_factory=Lane)
    runs: list[str] = field(default_factory=list[str])

    def __call__(self, spec: JobSpec) -> JobResult:
        self.runs.append(spec.key)
        lane = self.quick if isinstance(spec.budget, Quick) else self.background
        assert lane.gate.wait(LONG), "the test never opened the gate"
        if lane.error is not None:
            error, lane.error = lane.error, None if isinstance(lane.error, Stop) else lane.error
            raise error
        if lane.timeouts:
            lane.timeouts -= 1
            return measured("the check container ran past 60 s").model_copy(
                update={"timed_out": True}
            )
        return ran(spec, self.runs.count(spec.key))


def quick_only(root: Path) -> Plan:
    return Plan(quick=job(root), background=())


def with_fea(root: Path) -> Plan:
    return Plan(quick=job(root), background=(job(root, FEA),))


def wait_for(path: Path) -> None:
    deadline = time.monotonic() + LONG
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.01)


class Stop(BaseException):
    pass

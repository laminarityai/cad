import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from cad.checks import job_store
from cad.checks.jobs import Background, Charge, JobResult, JobSpec, Plan, Quick, Refused
from cad.checks.lanes import INTERRUPTED, Done, Lanes, Pending
from cad.checks.report import SPECS, build_request, unknown_for_all
from cad.checks.result import StepMissing
from cad.sandbox.outcome import SandboxUnavailable
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


@pytest.fixture
def runner() -> Iterator[GatedRunner]:
    made = GatedRunner()
    yield made
    made.quick.gate.set()
    made.background.gate.set()


def quick_only(root: Path) -> Plan:
    return Plan(quick=job(root), background=())


def with_fea(root: Path) -> Plan:
    return Plan(quick=job(root), background=(job(root, FEA),))


def wait_for(path: Path) -> None:
    deadline = time.monotonic() + LONG
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.01)


def test_a_second_settle_reads_the_stored_result_and_runs_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    first = lanes.settle(quick_only(tmp_path), 0)
    assert lanes.settle(quick_only(tmp_path), 0) == first
    assert Lanes(runner).settle(quick_only(tmp_path), 0) == first
    assert len(runner.runs) == 1


def test_a_tampered_result_runs_again_and_is_never_returned(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    honest = lanes.settle(quick_only(tmp_path), 0).quick
    path = job_store.result_path(job(tmp_path))
    path.write_bytes(path.read_bytes().replace(b'"unknown"', b'"pass"'))
    again = lanes.settle(quick_only(tmp_path), 0).quick
    assert len(runner.runs) == 2
    assert again == ran(job(tmp_path), 2) != honest
    assert job_store.read(job(tmp_path)) == again


def test_a_result_signed_for_another_job_is_not_trusted(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    lanes.settle(Plan(quick=job(tmp_path, material="prusament-petg"), background=()), 0)
    other = job_store.result_path(job(tmp_path, material="prusament-petg"))
    job_store.result_path(job(tmp_path)).write_bytes(other.read_bytes())
    lanes.settle(quick_only(tmp_path), 0)
    assert len(runner.runs) == 2


def test_concurrent_settles_of_one_job_run_it_once(tmp_path: Path, runner: GatedRunner) -> None:
    runner.quick.gate.clear()
    lanes = Lanes(runner)
    seen: list[JobResult] = []
    threads = [
        threading.Thread(target=lambda: seen.append(lanes.settle(quick_only(tmp_path), 0).quick))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    time.sleep(0.2)
    runner.quick.gate.set()
    for thread in threads:
        thread.join(LONG)
    assert seen == [ran(job(tmp_path))] * 4
    assert len(runner.runs) == 1


def test_a_background_job_still_running_after_the_wait_is_pending_then_done_once(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.gate.clear()
    lanes = Lanes(runner)
    started = time.monotonic()
    assert lanes.settle(with_fea(tmp_path), 0.2).background == (Pending(),)
    assert time.monotonic() - started >= 0.2
    assert lanes.settle(with_fea(tmp_path), 0).background == (Pending(),)
    runner.background.gate.set()
    wait_for(job_store.result_path(job(tmp_path, FEA)))
    assert lanes.settle(with_fea(tmp_path), 0).background == (Done(ran(job(tmp_path, FEA))),)
    assert len(runner.runs) == 2


def test_a_background_job_that_ends_within_the_wait_is_done(
    tmp_path: Path, runner: GatedRunner
) -> None:
    settled = Lanes(runner).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)


def test_a_killed_server_leaves_nothing_in_flight_and_the_next_one_runs_the_job(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.gate.clear()
    assert Lanes(runner).settle(with_fea(tmp_path), 0).background == (Pending(),)
    wait_for(job_store.result_path(job(tmp_path, FEA)).with_suffix(".attempt"))
    assert job_store.interrupted_runs(job(tmp_path, FEA)) == 1
    restarted = GatedRunner()
    settled = Lanes(restarted).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)
    assert restarted.runs == [job(tmp_path, FEA).key]
    assert job_store.interrupted_runs(job(tmp_path, FEA)) == 0


def test_a_job_interrupted_twice_is_refused_and_not_started_a_third_time(
    tmp_path: Path, runner: GatedRunner
) -> None:
    fea = job(tmp_path, FEA)
    job_store.begin_attempt(fea)
    job_store.begin_attempt(fea)
    settled = Lanes(runner).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Refused(INTERRUPTED),)
    assert job_store.read(fea) is None
    assert runner.runs == [job(tmp_path).key]


def test_a_background_job_that_fails_clears_its_attempt_and_is_not_stored(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.error = SandboxUnavailable("docker is not running")
    lanes = Lanes(runner)
    settled = lanes.settle(Plan(quick=job(tmp_path), background=(job(tmp_path, FEA),)), LONG)
    assert settled.background == (Refused("docker is not running"),)
    fea = job(tmp_path, FEA)
    assert (job_store.read(fea), job_store.interrupted_runs(fea)) == (None, 0)


def test_a_quick_job_that_fails_raises_stores_nothing_and_runs_again(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.quick.error = SandboxUnavailable("docker is not running")
    lanes = Lanes(runner)
    for _ in range(2):
        with pytest.raises(SandboxUnavailable, match="docker is not running"):
            lanes.settle(quick_only(tmp_path), 0)
    assert len(runner.runs) == 2
    assert job_store.read(job(tmp_path)) is None


def test_a_timed_out_run_is_returned_unstored_and_the_next_call_runs_again(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.quick.timeouts = 1
    lanes = Lanes(runner)
    first = lanes.settle(quick_only(tmp_path), 0).quick
    assert first.timed_out
    assert job_store.read(job(tmp_path)) is None
    second = lanes.settle(quick_only(tmp_path), 0).quick
    assert second == ran(job(tmp_path), 2) == job_store.read(job(tmp_path))
    assert Lanes(runner).settle(quick_only(tmp_path), 0).quick == second
    assert len(runner.runs) == 2


class Stop(BaseException):
    pass


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_worker_killed_by_a_base_exception_is_replaced(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.error = Stop()
    lanes = Lanes(runner)
    with pytest.raises(Stop):
        lanes.settle(with_fea(tmp_path), LONG)
    settled = lanes.settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA), 2)),)


class Closed:
    def admit(self, charge: Charge) -> Refused:
        del charge
        return Refused("the account has no analysis time left")


def test_a_refusing_meter_starts_no_background_job(tmp_path: Path, runner: GatedRunner) -> None:
    settled = Lanes(runner, Closed()).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Refused("the account has no analysis time left"),)
    assert runner.runs == [job(tmp_path).key]


def test_the_key_covers_the_shape_the_inputs_and_the_cited_rows(tmp_path: Path) -> None:
    plain = job(tmp_path)
    assert plain.key == job(tmp_path).key
    assert len(plain.key) == 20
    assert job(tmp_path, material="prusament-petg").key != plain.key
    assert replace(plain, brep_sha256="c" * 64).key != plain.key
    [(name, read)] = plain.request.reads.items()
    recited = replace(read, source=replace(read.source, page="another page"))
    request = replace(plain.request, reads={name: recited})
    assert request.wire == plain.request.wire
    assert replace(plain, request=request).key != plain.key


def test_a_peek_at_a_job_never_run_is_none_and_starts_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    assert Lanes(runner).peek(with_fea(tmp_path)) is None
    assert runner.runs == []


def test_a_peek_reads_the_stored_quick_result_and_calls_a_background_job_pending(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.gate.clear()
    lanes = Lanes(runner)
    plan = with_fea(tmp_path)
    quick = lanes.settle(quick_only(tmp_path), 0).quick
    runs = list(runner.runs)
    peeked = lanes.peek(plan)
    assert peeked is not None
    assert peeked.quick == quick
    assert peeked.background == (Pending(),)
    assert runner.runs == runs


def test_a_peek_reports_a_stored_background_result_as_done_and_runs_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    plan = with_fea(tmp_path)
    settled = lanes.settle(plan, LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)
    runs = list(runner.runs)
    assert lanes.peek(plan) == settled
    assert runner.runs == runs


def test_a_peek_does_not_trust_a_result_signed_for_another_job(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    lanes.settle(quick_only(tmp_path), 0)
    path = job_store.result_path(job(tmp_path))
    path.write_bytes(path.read_bytes().replace(b'"unknown"', b'"pass"'))
    assert lanes.peek(quick_only(tmp_path)) is None

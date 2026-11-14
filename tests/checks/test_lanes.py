import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from cad.checks import job_store
from cad.checks.jobs import JobResult, JobSpec, Plan, Refused
from cad.checks.lanes import INTERRUPTED, NOT_RUNNING, Done, Lanes, Pending
from cad.sandbox.meter import Kind, Reservation, charged, metered
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.lanes import (
    FEA,
    LONG,
    GatedRunner,
    Stop,
    job,
    quick_only,
    ran,
    wait_for,
    wait_until,
    with_fea,
)


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
    assert job_store.unfinished_runs(job(tmp_path, FEA)) == 1
    restarted = GatedRunner()
    settled = Lanes(restarted).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)
    assert restarted.runs == [job(tmp_path, FEA).key]
    assert job_store.unfinished_runs(job(tmp_path, FEA)) == 0


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


def test_the_interrupted_refusal_says_not_run_and_never_to_rebuild_the_same_shape() -> None:
    """A clean stop does not count, so two interruptions most likely mean the analysis kills its
    worker. A rebuild of the same shape would only buy two more crashes."""
    assert "report the check as not run" in INTERRUPTED
    assert "do not build the same shape again to retry it" in INTERRUPTED
    assert "change the variant's code" not in INTERRUPTED


def test_a_background_job_that_fails_clears_its_attempt_and_is_not_stored(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.error = SandboxUnavailable("docker is not running")
    lanes = Lanes(runner)
    settled = lanes.settle(Plan(quick=job(tmp_path), background=(job(tmp_path, FEA),)), LONG)
    assert settled.background == (Refused("docker is not running"),)
    fea = job(tmp_path, FEA)
    assert (job_store.read(fea), job_store.unfinished_runs(fea)) == (None, 0)


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


def test_a_peek_calls_a_background_job_pending_while_it_runs_here(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.gate.clear()
    lanes = Lanes(runner)
    plan = with_fea(tmp_path)
    quick = lanes.settle(plan, 0).quick
    runs = list(runner.runs)
    peeked = lanes.peek(plan)
    assert peeked is not None
    assert peeked.quick == quick
    assert peeked.background == (Pending(),)
    assert runner.runs == runs
    runner.background.gate.set()


def test_a_peek_after_a_restart_calls_a_job_no_process_runs_not_running_and_starts_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.gate.clear()
    Lanes(runner).settle(with_fea(tmp_path), 0)
    restarted = Lanes(runner)
    runs = list(runner.runs)
    peeked = restarted.peek(with_fea(tmp_path))
    assert peeked is not None
    assert peeked.background == (Refused(NOT_RUNNING),)
    assert "score the variant again" in NOT_RUNNING
    assert runner.runs == runs
    runner.background.gate.set()


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


def test_a_peek_while_the_rerun_of_an_interrupted_job_runs_calls_it_pending(
    tmp_path: Path, runner: GatedRunner
) -> None:
    fea = job(tmp_path, FEA)
    job_store.begin_attempt(fea)
    runner.background.gate.clear()
    lanes = Lanes(runner)
    assert lanes.settle(with_fea(tmp_path), 0).background == (Pending(),)
    wait_until(lambda: job_store.unfinished_runs(fea) == job_store.ATTEMPT_CAP)
    peeked = lanes.peek(with_fea(tmp_path))
    assert peeked is not None
    assert peeked.background == (Pending(),)
    runner.background.gate.set()
    wait_for(job_store.result_path(fea))
    assert lanes.settle(with_fea(tmp_path), 0).background == (Done(ran(fea)),)


def test_a_peek_does_not_trust_a_result_signed_for_another_job(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    lanes.settle(quick_only(tmp_path), 0)
    path = job_store.result_path(job(tmp_path))
    path.write_bytes(path.read_bytes().replace(b'"unknown"', b'"pass"'))
    assert lanes.peek(quick_only(tmp_path)) is None


@dataclass
class Charges:
    kinds: list[Kind] = field(default_factory=list[Kind])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        self.kinds.append(kind)
        return Reservation(str(len(self.kinds)), "2026-11-09", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation, seconds


def test_a_background_check_is_charged_to_the_account_that_asked(tmp_path: Path) -> None:
    def charging(spec: JobSpec) -> JobResult:
        with charged("check", 1):
            return ran(spec)

    charges = Charges()
    with metered(charges):
        settled = Lanes(charging).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)
    assert charges.kinds == ["check", "check"]

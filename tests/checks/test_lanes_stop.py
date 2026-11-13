import threading
import time
from pathlib import Path

from cad.checks import job_store
from cad.checks.jobs import JobSpec, Plan, Refused
from cad.checks.lanes import STOPPED, Done, Lanes, Outcome, Pending
from cad.sandbox.container import STOPPING
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.lanes import FEA, LONG, GatedRunner, job, ran, wait_until, with_fea


def running_once_interrupted(tmp_path: Path, runner: GatedRunner, lanes: Lanes) -> JobSpec:
    """An fea interrupted once before, now running again, so its count reads 2."""
    fea = job(tmp_path, FEA)
    job_store.begin_attempt(fea)
    runner.background.gate.clear()
    assert lanes.settle(with_fea(tmp_path), 0).background == (Pending(),)
    wait_until(lambda: job_store.interrupted_runs(fea) == job_store.ATTEMPT_CAP)
    return fea


class Waiting:
    """A caller settling `plan` on another thread, as a request does while a check runs."""

    def __init__(self, lanes: Lanes, plan: Plan) -> None:
        self._outcomes: list[tuple[Outcome, ...]] = []
        self._caller = threading.Thread(
            target=lambda: self._outcomes.append(lanes.settle(plan, LONG).background)
        )
        self._caller.start()
        time.sleep(0.2)

    def heard(self) -> tuple[Outcome, ...]:
        self._caller.join(LONG)
        (outcomes,) = self._outcomes
        return outcomes


def test_a_server_that_stops_mid_run_puts_the_attempt_count_back_and_stores_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    fea = running_once_interrupted(tmp_path, runner, lanes)
    waiting = Waiting(lanes, with_fea(tmp_path))
    lanes.close()
    assert job_store.interrupted_runs(fea) == 1
    runner.background.error = SandboxUnavailable(STOPPING)
    runner.background.gate.set()
    assert waiting.heard() == (Refused(STOPPING),)
    assert (job_store.read(fea), job_store.interrupted_runs(fea)) == (None, 1)
    restarted = GatedRunner()
    settled = Lanes(restarted).settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(fea)),)
    assert job_store.interrupted_runs(fea) == 0


def test_a_stopping_server_refuses_its_queued_jobs_and_never_starts_them(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    running_once_interrupted(tmp_path, runner, lanes)
    queued = job(tmp_path, FEA, material="prusament-petg")
    plan = Plan(quick=job(tmp_path), background=(queued,))
    waiting = Waiting(lanes, plan)
    lanes.close()
    assert waiting.heard() == (Refused(STOPPED),)
    assert lanes.settle(plan, 0).background == (Refused(STOPPED),)
    runner.background.gate.set()
    assert queued.key not in runner.runs
    assert job_store.interrupted_runs(queued) == 0

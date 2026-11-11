import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from cad.checks import job_store
from cad.checks.jobs import JobSpec, Plan, Refused
from cad.checks.lanes import SUPERSEDED, Done, Lanes
from cad.sandbox.outcome import SandboxUnavailable
from tests.support.lanes import (
    FEA,
    LONG,
    VID,
    GatedRunner,
    job,
    quick_only,
    ran,
    wait_for,
    with_fea,
)

OTHER = "fedcba9876543210"


class Heard:
    def __init__(self) -> None:
        self.jobs: list[JobSpec] = []
        self.stored: list[bool] = []
        self._changed = threading.Condition()

    def __call__(self, spec: JobSpec) -> None:
        stored = job_store.read(spec) is not None
        with self._changed:
            self.jobs.append(spec)
            self.stored.append(stored)
            self._changed.notify_all()

    def wait_for(self, count: int) -> None:
        """A background job's listeners run on the worker after its Future wakes the caller, so
        `settle` can return before they do."""
        with self._changed:
            assert self._changed.wait_for(lambda: len(self.jobs) >= count, LONG)


def other_variant(root: Path) -> JobSpec:
    (root / OTHER).mkdir(exist_ok=True)
    return replace(job(root, FEA, material="prusament-petg"), variant_id=OTHER)


def test_a_quick_and_a_background_completion_each_notify_once_with_the_result_stored(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    heard = Heard()
    lanes.subscribe(heard)
    lanes.settle(with_fea(tmp_path), LONG)
    heard.wait_for(2)
    assert sorted(one.key for one in heard.jobs) == sorted(
        [job(tmp_path).key, job(tmp_path, FEA).key]
    )
    assert heard.stored == [True, True]


def test_a_settle_that_finds_the_result_stored_notifies_nothing(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    lanes.settle(quick_only(tmp_path), 0)
    heard = Heard()
    lanes.subscribe(heard)
    lanes.settle(quick_only(tmp_path), 0)
    assert heard.jobs == []


def test_a_job_that_fails_notifies_nothing_because_the_store_did_not_change(
    tmp_path: Path, runner: GatedRunner
) -> None:
    runner.background.error = SandboxUnavailable("docker is not running")
    lanes = Lanes(runner)
    heard = Heard()
    lanes.settle(quick_only(tmp_path), 0)
    lanes.subscribe(heard)
    plan = with_fea(tmp_path)
    assert lanes.settle(plan, LONG).background == (Refused("docker is not running"),)
    assert heard.jobs == []


def test_a_listener_that_raises_is_logged_and_stops_nothing(
    tmp_path: Path, runner: GatedRunner, caplog: pytest.LogCaptureFixture
) -> None:
    lanes = Lanes(runner)
    heard = Heard()

    def raising(spec: JobSpec) -> None:
        raise RuntimeError(f"cannot tell anyone about {spec.key}")

    lanes.subscribe(raising)
    lanes.subscribe(heard)
    settled = lanes.settle(with_fea(tmp_path), LONG)
    assert settled.background == (Done(ran(job(tmp_path, FEA))),)
    heard.wait_for(2)
    assert [one.key for one in heard.jobs].count(job(tmp_path, FEA).key) == 1
    assert "a completion listener raised" in caplog.text
    plan = Plan(quick=job(tmp_path, material="prusament-petg"), background=())
    assert lanes.settle(plan, 0).quick == ran(plan.quick)
    assert len(heard.jobs) == 3


def test_an_unsubscribed_listener_hears_nothing_more_and_unsubscribing_twice_is_harmless(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    heard = Heard()
    unsubscribe = lanes.subscribe(heard)
    unsubscribe()
    unsubscribe()
    lanes.settle(quick_only(tmp_path), 0)
    assert heard.jobs == []


def queue_behind_a_running_job(
    tmp_path: Path, runner: GatedRunner, lanes: Lanes
) -> tuple[JobSpec, JobSpec]:
    runner.background.gate.clear()
    first, second = job(tmp_path, FEA), other_variant(tmp_path)
    lanes.settle(Plan(quick=job(tmp_path), background=(first,)), 0)
    wait_for(job_store.result_path(first).with_suffix(".attempt"))
    return first, second


def test_a_job_still_queued_when_its_variant_is_replaced_never_runs_and_its_caller_is_refused(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    first, second = queue_behind_a_running_job(tmp_path, runner, lanes)
    waiting: list[object] = []
    caller = threading.Thread(
        target=lambda: waiting.append(
            lanes.settle(Plan(quick=job(tmp_path), background=(second,)), LONG).background
        )
    )
    caller.start()
    time.sleep(0.2)
    assert lanes.drop_unstarted(tmp_path, OTHER) == 1
    caller.join(LONG)
    assert waiting == [(Refused(SUPERSEDED),)]
    runner.background.gate.set()
    wait_for(job_store.result_path(first))
    assert second.key not in runner.runs
    assert job_store.read(second) is None
    assert job_store.interrupted_runs(second) == 0


def test_a_job_a_worker_already_took_is_not_dropped_and_ends_stored(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    first, _ = queue_behind_a_running_job(tmp_path, runner, lanes)
    assert lanes.drop_unstarted(tmp_path, VID) == 0
    runner.background.gate.set()
    wait_for(job_store.result_path(first))
    assert job_store.read(first) == ran(first)


def test_a_drop_names_one_variant_in_one_store_and_leaves_the_rest_queued(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    _, second = queue_behind_a_running_job(tmp_path, runner, lanes)
    lanes.settle(Plan(quick=job(tmp_path), background=(second,)), 0)
    assert lanes.drop_unstarted(tmp_path / "another-account", OTHER) == 0
    assert lanes.drop_unstarted(tmp_path, "0" * 16) == 0
    runner.background.gate.set()
    wait_for(job_store.result_path(second))
    assert job_store.read(second) == ran(second)


def test_a_dropped_job_runs_again_when_its_variant_is_scored_again(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    _, second = queue_behind_a_running_job(tmp_path, runner, lanes)
    lanes.settle(Plan(quick=job(tmp_path), background=(second,)), 0)
    assert lanes.drop_unstarted(tmp_path, OTHER) == 1
    runner.background.gate.set()
    again = lanes.settle(Plan(quick=job(tmp_path), background=(second,)), LONG)
    assert again.background == (Done(ran(second)),)


def test_a_drop_notifies_nobody_because_the_store_did_not_change(
    tmp_path: Path, runner: GatedRunner
) -> None:
    lanes = Lanes(runner)
    _, second = queue_behind_a_running_job(tmp_path, runner, lanes)
    lanes.settle(Plan(quick=job(tmp_path), background=(second,)), 0)
    heard = Heard()
    lanes.subscribe(heard)
    lanes.drop_unstarted(tmp_path, OTHER)
    assert heard.jobs == []

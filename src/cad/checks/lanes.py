import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.checks import job_store
from cad.checks.jobs import (
    Background,
    JobResult,
    JobSpec,
    Meter,
    Plan,
    Quick,
    Refused,
    Unmetered,
    run_quick,
)
from cad.sandbox.outcome import SandboxUnavailable

WAIT_SECONDS: Final = 20
INTERRUPTED: Final = (
    f"the analysis was interrupted {job_store.ATTEMPT_CAP} times, so it was not started again; "
    "the operator can delete its .attempt file to retry it"
)

type Run = Callable[[JobSpec], JobResult]


@dataclass(frozen=True, slots=True)
class Done:
    result: JobResult


@dataclass(frozen=True, slots=True)
class Pending:
    pass


type Outcome = Done | Pending | Refused


@dataclass(frozen=True, slots=True)
class Settled:
    quick: JobResult
    background: tuple[Outcome, ...]


class Lanes:
    def __init__(self, run: Run, meter: Meter | None = None) -> None:
        self._run = run
        self._meter = meter or Unmetered()
        self._lock = threading.Lock()
        self._flying: dict[Path, Future[JobResult]] = {}
        self._queue = queue.SimpleQueue[tuple[JobSpec, Future[JobResult]]]()
        self._worker: threading.Thread | None = None

    def settle(self, plan: Plan, wait_seconds: float) -> Settled:
        deadline = time.monotonic() + wait_seconds
        flights = tuple(self._take_off(job) for job in plan.background)
        quick = self._take_off(plan.quick)
        assert not isinstance(quick, Refused), "only background jobs are refused"
        result = quick.result if isinstance(quick, Done) else quick.result()
        return Settled(result, tuple(_land(flight, deadline) for flight in flights))

    def _take_off(self, job: JobSpec) -> Done | Refused | Future[JobResult]:
        path = job_store.result_path(job)
        with self._lock:
            flying = self._flying.get(path)
            if flying is not None:
                return flying
            stored = job_store.read(job)
            if stored is not None:
                return Done(stored)
            refused = self._refusal(job)
            if refused is not None:
                return refused
            future = Future[JobResult]()
            self._flying[path] = future
        match job.budget:
            case Quick():
                self._fly(job, future)
            case Background():
                self._enqueue(job, future)
        return future

    def _refusal(self, job: JobSpec) -> Refused | None:
        if isinstance(job.budget, Quick):
            return None
        if job_store.interrupted_runs(job) >= job_store.ATTEMPT_CAP:
            return Refused(INTERRUPTED)
        admitted = self._meter.admit(job)
        return admitted if isinstance(admitted, Refused) else None

    def _fly(self, job: JobSpec, future: Future[JobResult]) -> None:
        try:
            result = self._attempt(job)
            job_store.write(job, result)
        except BaseException as error:
            future.set_exception(error)
            if not isinstance(error, Exception):
                raise
        else:
            future.set_result(result)
        finally:
            with self._lock:
                del self._flying[job_store.result_path(job)]

    def _attempt(self, job: JobSpec) -> JobResult:
        if isinstance(job.budget, Quick):
            return self._run(job)
        job_store.begin_attempt(job)
        try:
            return self._run(job)
        finally:
            job_store.end_attempt(job)

    def _enqueue(self, job: JobSpec, future: Future[JobResult]) -> None:
        self._queue.put((job, future))
        with self._lock:
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._drain, name="cad-background", daemon=True
                )
                self._worker.start()

    def _drain(self) -> None:
        while True:
            self._fly(*self._queue.get())


def _land(flight: Done | Refused | Future[JobResult], deadline: float) -> Outcome:
    if not isinstance(flight, Future):
        return flight
    try:
        return Done(flight.result(timeout=max(0.0, deadline - time.monotonic())))
    except TimeoutError:
        return Pending()
    except SandboxUnavailable as error:
        return Refused(str(error))


LANES: Final = Lanes(run_quick)

import contextvars
import queue
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.checks import job_store
from cad.checks.container.check import Background, Quick
from cad.checks.jobs import JobResult, JobSpec, Plan, Refused, run_job
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
    def __init__(self, run: Run) -> None:
        self._run = run
        self._lock = threading.Lock()
        self._flying: dict[Path, Future[JobResult]] = {}
        self._queue = queue.SimpleQueue[tuple[contextvars.Context, JobSpec, Future[JobResult]]]()
        self._worker: threading.Thread | None = None

    def settle(self, plan: Plan, wait_seconds: float) -> Settled:
        deadline = time.monotonic() + wait_seconds
        flights = tuple(self._take_off(job) for job in plan.background)
        quick = self._take_off(plan.quick)
        assert not isinstance(quick, Refused), "only background jobs are refused"
        result = quick.result if isinstance(quick, Done) else quick.result()
        return Settled(result, tuple(_land(flight, deadline) for flight in flights))

    def peek(self, plan: Plan) -> Settled | None:
        """What the store holds for `plan`, with no wait and no job started. A background job is
        done when its result is stored, refused when it was interrupted too often, and pending
        otherwise. None when the quick result is not stored: the variant was never scored."""
        quick = job_store.read(plan.quick)
        if quick is None:
            return None
        return Settled(quick, tuple(self._look(job) for job in plan.background))

    def _look(self, job: JobSpec) -> Outcome:
        stored = job_store.read(job)
        if stored is not None:
            return Done(stored)
        if job_store.interrupted_runs(job) >= job_store.ATTEMPT_CAP:
            return Refused(INTERRUPTED)
        return Pending()

    def _take_off(self, job: JobSpec) -> Done | Refused | Future[JobResult]:
        path = job_store.result_path(job)
        with self._lock:
            stored = job_store.read(job)
            if stored is not None:
                return Done(stored)
            flying = self._flying.get(path)
            if flying is not None:
                return flying
            if _interrupted_too_often(job):
                return Refused(INTERRUPTED)
            future = Future[JobResult]()
            self._flying[path] = future
        match job.budget:
            case Quick():
                self._fly(job, future)
            case Background():
                self._enqueue(job, future)
        return future

    def _fly(self, job: JobSpec, future: Future[JobResult]) -> None:
        """The Future leaves _flying in the same lock that settles it, so a caller woken by it
        never takes it off again: a failed job then runs again, and a done one reads the store."""
        try:
            result = self._attempt(job)
            job_store.write(job, result)
        except BaseException as error:
            with self._lock:
                del self._flying[job_store.result_path(job)]
                future.set_exception(error)
            if not isinstance(error, Exception):
                raise
        else:
            with self._lock:
                del self._flying[job_store.result_path(job)]
                future.set_result(result)

    def _attempt(self, job: JobSpec) -> JobResult:
        if isinstance(job.budget, Quick):
            return self._run(job)
        job_store.begin_attempt(job)
        try:
            return self._run(job)
        finally:
            job_store.end_attempt(job)

    def _enqueue(self, job: JobSpec, future: Future[JobResult]) -> None:
        """The job runs in a copy of the caller's context, so its container is charged to the
        caller's account."""
        self._queue.put((contextvars.copy_context(), job, future))
        with self._lock:
            if self._worker is None:
                self._start_worker()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._drain, name="cad-background", daemon=True)
        self._worker.start()

    def _drain(self) -> None:
        try:
            while True:
                context, job, future = self._queue.get()
                context.run(self._fly, job, future)
        finally:
            with self._lock:
                self._worker = None
                if not self._queue.empty():
                    self._start_worker()


def _interrupted_too_often(job: JobSpec) -> bool:
    return (
        isinstance(job.budget, Background)
        and job_store.interrupted_runs(job) >= job_store.ATTEMPT_CAP
    )


def _land(flight: Done | Refused | Future[JobResult], deadline: float) -> Outcome:
    if not isinstance(flight, Future):
        return flight
    try:
        return Done(flight.result(timeout=max(0.0, deadline - time.monotonic())))
    except TimeoutError:
        return Pending()
    except SandboxUnavailable as error:
        return Refused(str(error))


LANES: Final = Lanes(run_job)

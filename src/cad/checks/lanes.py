import contextvars
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Collection, Iterable
from concurrent.futures import Future
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.checks import job_store
from cad.checks.container.check import Background, Quick
from cad.checks.jobs import JobResult, JobSpec, Plan, Refused, run_job
from cad.sandbox.outcome import SandboxUnavailable

WAIT_SECONDS: Final = 20
INTERRUPTED: Final = (
    f"the analysis did not finish for this variant in {job_store.ATTEMPT_CAP} tries and will not "
    "run again for it; report the check as not run, and do not build the same shape again to "
    "retry it. A revision that changes the shape is analysed as usual"
)

SUPERSEDED: Final = (
    "a newer revision replaced this variant in its slot before this analysis started, so it was "
    "dropped; score the variant again to run it"
)
NOT_RUNNING: Final = (
    "the analysis is not running for this variant and has no stored result, as after a restart "
    "or a failed run; score the variant again to run it"
)
STOPPED: Final = (
    "the server is stopping, so this analysis was not started; score the variant again once the "
    "server is back"
)
LOG: Final = logging.getLogger(__name__)

type Run = Callable[[JobSpec], JobResult]
type Listener = Callable[[JobSpec], None]
type Queued = tuple[contextvars.Context, JobSpec, Future[JobResult]]


class Superseded(Exception):
    pass


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
        self._wake = threading.Condition(self._lock)
        self._flying: dict[Path, Future[JobResult]] = {}
        self._queue = deque[Queued]()
        self._worker: threading.Thread | None = None
        self._listeners: list[Listener] = []
        self._running: JobSpec | None = None
        self._closed = False

    def settle(self, plan: Plan, wait_seconds: float) -> Settled:
        deadline = time.monotonic() + wait_seconds
        flights = tuple(self._take_off(job) for job in plan.background)
        quick = self._take_off(plan.quick)
        assert not isinstance(quick, Refused), "only background jobs are refused"
        result = quick.result if isinstance(quick, Done) else quick.result()
        return Settled(result, tuple(_land(flight, deadline) for flight in flights))

    def peek(self, plan: Plan) -> Settled | None:
        """What the store holds for `plan`, with no wait and no job started. A background job is
        done when its result is stored and pending only while it is queued or runs here.
        Otherwise it is refused: interrupted too often, or not running. None when the quick
        result is not stored: the variant was never scored."""
        quick = job_store.read(plan.quick)
        if quick is None:
            return None
        return Settled(quick, tuple(self._look(job) for job in plan.background))

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Call `listener(job)` after each job of this process stores its result, on the thread
        that ran it. A listener that raises is logged and does not stop the job's callers, the
        worker or the other listeners. The returned function removes it."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock, suppress(ValueError):
                self._listeners.remove(listener)

        return unsubscribe

    def drop_unstarted(self, root: Path, replaced: Callable[[], Collection[str]]) -> int:
        """Drop the queued background jobs of each variant that `replaced` names, for revisions
        a newer one replaced. `replaced` runs under the lock that queues jobs, so its answer
        holds for every job in the queue. A job a worker already took runs on and is stored. A
        caller waiting on a dropped job is refused. Returns how many were dropped."""
        with self._lock:
            gone = replaced()
            kept = deque[Queued]()
            dropped = deque[Queued]()
            for item in self._queue:
                _, job, _ = item
                (dropped if job.root == root and job.variant_id in gone else kept).append(item)
            self._queue = kept
            self._refuse_locked(dropped, lambda: Superseded(SUPERSEDED))
        return len(dropped)

    def close(self) -> None:
        """Take no more background jobs, for a server that is stopping. A queued job is refused
        before it starts, and the running job's attempt is taken back, because the server ends
        that run, not the job. Call it before the server removes its containers."""
        with self._lock:
            self._closed = True
            self._refuse_locked(self._queue, lambda: SandboxUnavailable(STOPPED))
            self._queue.clear()
            running, self._running = self._running, None
            if running is not None:
                job_store.undo_attempt(running)

    def _refuse_locked(self, queued: Iterable[Queued], error: Callable[[], Exception]) -> None:
        for _, job, future in queued:
            del self._flying[job_store.result_path(job)]
            future.set_exception(error())

    def _look(self, job: JobSpec) -> Outcome:
        with self._lock:
            stored = job_store.read(job)
            if stored is not None:
                return Done(stored)
            if job_store.result_path(job) in self._flying:
                return Pending()
            return Refused(INTERRUPTED if _interrupted_too_often(job) else NOT_RUNNING)

    def _take_off(self, job: JobSpec) -> Done | Refused | Future[JobResult]:
        path = job_store.result_path(job)
        with self._lock:
            stored = job_store.read(job)
            if stored is not None:
                return Done(stored)
            flying = self._flying.get(path)
            if flying is not None:
                return flying
            if self._closed and isinstance(job.budget, Background):
                return Refused(STOPPED)
            if _interrupted_too_often(job):
                return Refused(INTERRUPTED)
            future = Future[JobResult]()
            self._flying[path] = future
            if isinstance(job.budget, Background):
                self._enqueue_locked(job, future)
        if isinstance(job.budget, Quick):
            self._fly(job, future)
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
                listeners = tuple(self._listeners)
            for listener in listeners:
                try:
                    listener(job)
                except Exception:
                    LOG.exception("a completion listener raised for variant %s", job.variant_id)

    def _attempt(self, job: JobSpec) -> JobResult:
        if isinstance(job.budget, Quick):
            return self._run(job)
        with self._lock:
            if self._closed:
                raise SandboxUnavailable(STOPPED)
            job_store.begin_attempt(job)
            self._running = job
        try:
            return self._run(job)
        finally:
            with self._lock:
                if self._running is job:
                    self._running = None
                    job_store.end_attempt(job)

    def _enqueue_locked(self, job: JobSpec, future: Future[JobResult]) -> None:
        """The job runs in a copy of the caller's context, so its container is charged to the
        caller's account."""
        self._queue.append((contextvars.copy_context(), job, future))
        self._wake.notify()
        if self._worker is None:
            self._start_worker()

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._drain, name="cad-background", daemon=True)
        self._worker.start()

    def _drain(self) -> None:
        try:
            while True:
                with self._lock:
                    while not self._queue:
                        self._wake.wait()
                    context, job, future = self._queue.popleft()
                context.run(self._fly, job, future)
        finally:
            with self._lock:
                self._worker = None
                if self._queue:
                    self._start_worker()


def _interrupted_too_often(job: JobSpec) -> bool:
    return (
        isinstance(job.budget, Background)
        and job_store.unfinished_runs(job) >= job_store.ATTEMPT_CAP
    )


def _land(flight: Done | Refused | Future[JobResult], deadline: float) -> Outcome:
    if not isinstance(flight, Future):
        return flight
    try:
        return Done(flight.result(timeout=max(0.0, deadline - time.monotonic())))
    except TimeoutError:
        return Pending()
    except (SandboxUnavailable, Superseded) as error:
        return Refused(str(error))


LANES: Final = Lanes(run_job)

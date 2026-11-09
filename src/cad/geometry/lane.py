import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Final

from cad.geometry import job, store
from cad.geometry.model import GeometryRead, TessellationPending
from cad.variants.entry import Entry

type Run = Callable[[bytes, str], job.Ran]


class Tessellations:
    """Each BREP is tessellated at most once at a time, in the background, and once stored it is
    read from the store with no job."""

    def __init__(self, run: Run = job.tessellate) -> None:
        self._run = run
        self._lock = threading.Lock()
        self._flying: dict[Path, Future[job.Ran]] = {}

    def read(self, root: Path, held: Entry, wait_seconds: float = 0.0) -> GeometryRead:
        """The stored mesh, or the outcome of a job started for it that ends within
        `wait_seconds`, or pending. A job that raised, such as with Docker down, raises here."""
        stored = store.read(root, held.brep_sha256)
        if stored is not None:
            return stored
        try:
            return self._take_off(root, held).result(timeout=wait_seconds).read
        except TimeoutError:
            return TessellationPending(brep_sha256=held.brep_sha256)

    def _take_off(self, root: Path, held: Entry) -> Future[job.Ran]:
        key = store.path(root, held.brep_sha256)
        with self._lock:
            flying = self._flying.get(key)
            if flying is not None:
                return flying
            future = Future[job.Ran]()
            self._flying[key] = future
        threading.Thread(
            target=self._fly, args=(root, held, key, future), name="cad-tessellate", daemon=True
        ).start()
        return future

    def _fly(self, root: Path, held: Entry, key: Path, future: Future[job.Ran]) -> None:
        outcome: job.Ran | Exception
        try:
            outcome = self._run(held.brep, held.brep_sha256)
            if outcome.lasting:
                store.write(root, outcome.read)
        except Exception as error:
            outcome = error
        # Removed before the future resolves, so a read after it starts a new job.
        with self._lock:
            del self._flying[key]
        if isinstance(outcome, Exception):
            future.set_exception(outcome)
        else:
            future.set_result(outcome)


TESSELLATIONS: Final = Tessellations()

from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Final

from cad.geometry import job, store
from cad.geometry.flights import Flights
from cad.geometry.model import GeometryRead, TessellationPending
from cad.variants.entry import Entry

type Run = Callable[[bytes, str], job.Ran]


class Tessellations:
    """Each BREP is tessellated at most once at a time, in the background, and once stored it is
    read from the store with no job."""

    def __init__(self, run: Run = job.tessellate) -> None:
        self._run = run
        self._flights = Flights[job.Ran]("cad-tessellate")

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
        return self._flights.take_off(
            store.path(root, held.brep_sha256), lambda: self._tessellate(root, held)
        )

    def _tessellate(self, root: Path, held: Entry) -> job.Ran:
        outcome = self._run(held.brep, held.brep_sha256)
        if outcome.lasting:
            store.write(root, outcome.read)
        return outcome


TESSELLATIONS: Final = Tessellations()

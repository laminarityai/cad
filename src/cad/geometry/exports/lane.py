from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Final

from cad.geometry.exports import job, store
from cad.geometry.exports.model import Exported, ExportFailed, ExportPending, ExportRead
from cad.geometry.flights import Flights
from cad.sandbox.bodies import Bodies
from cad.sandbox.outcome import Areas
from cad.variants.entry import Entry

type Run = Callable[[bytes, str, Areas, Bodies], job.Ran]


class Exports:
    """Each BREP, with the areas its build code coloured and the bodies it named, is exported at
    most once at a time, in the background, and once stored it is read with no job."""

    def __init__(self, run: Run = job.export) -> None:
        self._run = run
        self._flights = Flights[Exported | ExportFailed]("cad-export")

    def read(self, root: Path, held: Entry, wait_seconds: float = 0.0) -> ExportRead:
        """The stored record, or the outcome of a job started for it that ends within
        `wait_seconds`, or pending. A job that raised, such as with Docker down, raises here."""
        stored = store.read(root, key_of(held))
        if stored is not None:
            return stored
        try:
            return self._take_off(root, held).result(timeout=wait_seconds)
        except TimeoutError:
            return ExportPending(key=key_of(held))

    def _take_off(self, root: Path, held: Entry) -> Future[Exported | ExportFailed]:
        return self._flights.take_off(
            store.path(root, key_of(held), "json"), lambda: self._export(root, held)
        )

    def _export(self, root: Path, held: Entry) -> Exported | ExportFailed:
        # A read that found nothing stored can take off just after the last job stored its record
        # and landed, so the flight looks again before it runs a job.
        stored = store.read(root, key_of(held))
        if stored is not None:
            return stored
        outcome = self._run(held.brep, key_of(held), held.areas, held.bodies)
        if outcome.lasting:
            store.write(root, outcome)
        return outcome.read


def key_of(held: Entry) -> str:
    return job.key_of(held.brep_sha256, held.areas, held.bodies)


EXPORTS: Final = Exports()

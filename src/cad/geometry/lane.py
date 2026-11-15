from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Final, Protocol

from cad.geometry import job, store
from cad.geometry.flights import Flights
from cad.geometry.model import GeometryRead, Tessellated, TessellationFailed, TessellationPending

type Run = Callable[[bytes, str], job.Ran]


class Brep(Protocol):
    """Any BREP by its SHA-256: a variant's built shape, or a part a person supplied. `brep` is
    read only when no mesh of it is stored."""

    @property
    def brep(self) -> bytes: ...

    @property
    def brep_sha256(self) -> str: ...


class Tessellations:
    """Each BREP is tessellated at most once at a time, in the background, and once stored it is
    read from the store with no job. A failure that is not stored, such as a timeout, is held
    until one read reports it, so a poller sees the job end, and the read after that runs the
    job again."""

    def __init__(self, run: Run = job.tessellate) -> None:
        self._run = run
        self._flights = Flights[Tessellated | TessellationFailed]("cad-tessellate")
        self._brief: dict[Path, TessellationFailed] = {}

    def read(self, root: Path, held: Brep, wait_seconds: float = 0.0) -> GeometryRead:
        """The stored mesh or a held failure, or the outcome of a job started for it that ends
        within `wait_seconds`, or pending. A job that raised, such as with Docker down, raises
        here."""
        stored = store.read(root, held.brep_sha256) or self._reported(root, held)
        if stored is not None:
            return stored
        try:
            outcome = self._take_off(root, held).result(timeout=wait_seconds)
        except TimeoutError:
            return TessellationPending(brep_sha256=held.brep_sha256)
        self._reported(root, held)
        return outcome

    def start(self, root: Path, held: Brep) -> Tessellated | TessellationFailed | None:
        """The stored mesh or a held failure, or None once a job is making it. Unlike `read`, it
        never waits and never raises: a job that raised is started again by the next call."""
        stored = store.read(root, held.brep_sha256) or self._reported(root, held)
        if stored is None:
            self._take_off(root, held)
        return stored

    def _reported(self, root: Path, held: Brep) -> TessellationFailed | None:
        return self._brief.pop(store.path(root, held.brep_sha256), None)

    def _take_off(self, root: Path, held: Brep) -> Future[Tessellated | TessellationFailed]:
        return self._flights.take_off(
            store.path(root, held.brep_sha256), lambda: self._tessellate(root, held)
        )

    def _tessellate(self, root: Path, held: Brep) -> Tessellated | TessellationFailed:
        # A read that found nothing stored can take off just after the last job stored its mesh
        # and landed, so the flight looks again before it runs a job.
        stored = store.read(root, held.brep_sha256)
        if stored is not None:
            return stored
        outcome = self._run(held.brep, held.brep_sha256)
        if outcome.lasting:
            store.write(root, outcome.read)
        elif isinstance(outcome.read, TessellationFailed):
            self._brief[store.path(root, held.brep_sha256)] = outcome.read
        return outcome.read


TESSELLATIONS: Final = Tessellations()

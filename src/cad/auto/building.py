"""The builds under each Auto run that this process has started and not yet counted.

A person's Stop can land while a container runs, after which the run log takes no more records.
The stop records whether such a build was still running, so the report says so instead of
guessing a number. The hosted app runs one process, so this sees every build under a run."""

import threading
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from typing import Final

from cad.auto.model import Running

_LOCK: Final = threading.Lock()
_RUNNING: Final[Counter[tuple[str, str]]] = Counter()


@contextmanager
def building(run_id: str | None, code_sha256: str) -> Generator[None]:
    """Enter before the run's gate, so a stop that the gate does not see finds the build here."""
    if run_id is None:
        yield
        return
    key = (run_id, code_sha256)
    with _LOCK:
        _RUNNING[key] += 1
    try:
        yield
    finally:
        with _LOCK:
            _RUNNING[key] -= 1
            if not _RUNNING[key]:
                del _RUNNING[key]


def uncounted(run_id: str, state: Running) -> bool:
    """A build under the run is running and its code is not among the run's builds yet."""
    with _LOCK:
        return any(run == run_id and sha not in state.builds for run, sha in _RUNNING)

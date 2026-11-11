import contextvars
import threading
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path


class Flights[T]:
    """Each key's work runs at most once at a time, on a background thread. A second ask for a key
    in flight gets the first one's future, so the work never runs twice side by side."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._lock = threading.Lock()
        self._flying: dict[Path, Future[T]] = {}

    def take_off(self, key: Path, work: Callable[[], T]) -> Future[T]:
        with self._lock:
            flying = self._flying.get(key)
            if flying is not None:
                return flying
            future = Future[T]()
            self._flying[key] = future
        # The work runs in a copy of the caller's context, so its container is charged to the
        # account whose meter that context binds.
        context = contextvars.copy_context()
        threading.Thread(
            target=context.run,
            args=(self._fly, key, work, future),
            name=self._name,
            daemon=True,
        ).start()
        return future

    def _fly(self, key: Path, work: Callable[[], T], future: Future[T]) -> None:
        outcome: T | Exception
        try:
            outcome = work()
        except Exception as error:
            outcome = error
        # Removed before the future resolves, so a read after it starts new work.
        with self._lock:
            del self._flying[key]
        if isinstance(outcome, Exception):
            future.set_exception(outcome)
        else:
            future.set_result(outcome)

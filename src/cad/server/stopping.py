import signal
from collections.abc import Generator
from contextlib import contextmanager, suppress
from types import FrameType

from cad.checks.lanes import LANES, Lanes
from cad.sandbox import container
from cad.sandbox.outcome import SandboxUnavailable


@contextmanager
def checks_end_with_the_server(lanes: Lanes = LANES) -> Generator[None]:
    """A server that stops ends its own checks first, so a deploy never counts as an interrupted
    run and leaves no container behind. uvicorn catches SIGTERM for its graceful shutdown, then
    raises it again once that ends, so the handler below runs last. It then dies by SIGTERM, as a
    server with no handler would. Call it on the main thread."""

    def on_sigterm(signum: int, frame: FrameType | None) -> None:
        signal.signal(signum, signal.SIG_DFL)
        end_checks(lanes)
        signal.raise_signal(signum)

    previous = signal.signal(signal.SIGTERM, on_sigterm)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
        end_checks(lanes)


def end_checks(lanes: Lanes) -> None:
    with suppress(SandboxUnavailable):
        lanes.close()
    with suppress(SandboxUnavailable):
        container.stop_owned()

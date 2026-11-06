"""Runs inside the sandbox container only, as `python -I -c <this source> <wall seconds>`.

The host sends this source with every build, so the image holds only Python and the locked
packages, and editing this file never needs an image rebuild. It imports only the standard library
when it runs. Variant code arrives on stdin, and one `wire.Report` leaves on the original stdout.
"""

from __future__ import annotations

import importlib
import io
import json
import os
import resource
import runpy
import sys
import traceback
from base64 import b64encode
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from types import TracebackType

    from cad.sandbox.wire import FailedReport, Report

VARIANT = Path("/tmp/variant.py")
CPU_GRACE_SECONDS = 5
STEP_TIMESTAMP = "2000-01-01T00:00:00"
"""A fixed STEP header timestamp, so the same shape exports to the same bytes."""


class Build123d(Protocol):
    Shape: type[object]

    def export_brep(self, to_export: object, file_path: io.BytesIO) -> bool: ...

    def export_step(self, to_export: object, file_path: io.BytesIO, *, timestamp: str) -> bool: ...


def main() -> None:
    root = os.getpid()
    report_channel = os.dup(1)
    os.dup2(2, 1)
    report = run_variant(root, int(sys.argv[1]))
    sys.stdout.flush()
    sys.stderr.flush()
    with os.fdopen(report_channel, "wb") as channel:
        channel.write(json.dumps(report).encode())
    # Skips interpreter shutdown, so the variant's atexit hooks and threads never run after this.
    os._exit(0)


def run_variant(root: int, wall_seconds: int) -> Report:
    """Run the code as `__main__`, then report on its `result`. Only `root` returns."""
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (wall_seconds, wall_seconds + CPU_GRACE_SECONDS))
        VARIANT.write_bytes(sys.stdin.buffer.read())
        namespace = runpy.run_path(str(VARIANT), run_name="__main__")
    except BaseException as error:
        leave_unless(root)
        return failed(error)
    leave_unless(root)
    try:
        return result_report(namespace)
    except BaseException as error:
        return failed(error)


def leave_unless(root: int) -> None:
    """A process the variant forked ends here, so it never writes a report."""
    if os.getpid() != root:
        os._exit(0)


def result_report(namespace: dict[str, object]) -> Report:
    if "result" not in namespace:
        return {"kind": "no_result", "found": None}
    shape = namespace["result"]
    build123d = cast(Build123d, importlib.import_module("build123d"))
    if not isinstance(shape, build123d.Shape):
        return {"kind": "no_result", "found": type(shape).__name__}
    brep, step = io.BytesIO(), io.BytesIO()
    if not build123d.export_brep(shape, brep):
        raise RuntimeError("build123d could not export `result` as BREP")
    if not build123d.export_step(shape, step, timestamp=STEP_TIMESTAMP):
        raise RuntimeError("build123d could not export `result` as STEP")
    return {
        "kind": "built",
        "brep": b64encode(brep.getvalue()).decode(),
        "step": b64encode(step.getvalue()).decode(),
    }


def failed(error: BaseException) -> FailedReport:
    lines = traceback.format_exception(type(error), error, variant_frames(error.__traceback__))
    summary = traceback.format_exception_only(error)
    # The "Type: message" entry comes after a SyntaxError's source lines and before any notes.
    line = summary[-1] if isinstance(error, SyntaxError) else summary[0]
    return {
        "kind": "build_failed",
        "error": line.strip(),
        "traceback": "".join(lines),
    }


def variant_frames(frames: TracebackType | None) -> TracebackType | None:
    """Drop the runner's and runpy's frames, so the traceback starts in the variant's code."""
    while frames is not None and frames.tb_frame.f_code.co_filename != str(VARIANT):
        frames = frames.tb_next
    return frames


if __name__ == "__main__":
    main()

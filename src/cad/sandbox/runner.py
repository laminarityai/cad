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
CPU_KILL_AFTER_SECONDS = 5
REPRODUCIBLE_STEP_TIMESTAMP = "2000-01-01T00:00:00"


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


def run_variant(root: int, cpu_seconds: int) -> Report:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + CPU_KILL_AFTER_SECONDS))
        VARIANT.write_bytes(sys.stdin.buffer.read())
        namespace = runpy.run_path(str(VARIANT), run_name="__main__")
    except BaseException as error:
        exit_if_forked_child(root)
        return failed(error)
    exit_if_forked_child(root)
    try:
        return result_report(namespace)
    except BaseException as error:
        return failed(error)


def exit_if_forked_child(root: int) -> None:
    if os.getpid() != root:
        os._exit(0)


def result_report(namespace: dict[str, object]) -> Report:
    if "result" not in namespace:
        return {"kind": "no_result"}
    shape = namespace["result"]
    build123d = cast(Build123d, importlib.import_module("build123d"))
    if not isinstance(shape, build123d.Shape):
        return {"kind": "not_a_shape", "found": utf8(type(shape).__name__)}
    brep, step = io.BytesIO(), io.BytesIO()
    if not build123d.export_brep(shape, brep):
        raise RuntimeError("build123d could not export `result` as BREP")
    if not build123d.export_step(shape, step, timestamp=REPRODUCIBLE_STEP_TIMESTAMP):
        raise RuntimeError("build123d could not export `result` as STEP")
    return {
        "kind": "built",
        "brep": b64encode(brep.getvalue()).decode(),
        "step": b64encode(step.getvalue()).decode(),
    }


def failed(error: BaseException) -> FailedReport:
    lines = traceback.format_exception(type(error), error, variant_frames(error.__traceback__))
    summary = traceback.format_exception_only(error)
    # format_exception_only puts one entry per note after the "Type: message" entry.
    notes = getattr(error, "__notes__", ())
    return {
        "kind": "build_failed",
        "error": utf8(summary[-1 - len(notes)].strip()),
        "traceback": utf8("".join(lines)),
    }


def utf8(text: str) -> str:
    """The host rejects JSON holding a lone surrogate, so the report must not carry one."""
    return text.encode("utf-8", "replace").decode("utf-8")


def variant_frames(frames: TracebackType | None) -> TracebackType | None:
    while frames is not None and frames.tb_frame.f_code.co_filename != str(VARIANT):
        frames = frames.tb_next
    return frames


if __name__ == "__main__":
    main()

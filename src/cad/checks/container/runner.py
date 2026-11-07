import base64
import json
import os
import resource
import sys
from collections.abc import Callable
from typing import cast

from cad.checks.container.check import Subject, finding
from cad.checks.container.kernel import (
    Kernel,
    Shape,
    StepTooLarge,
    Unreadable,
    first_line,
    ocp_kernel,
)
from cad.checks.container.suite import CHECKS
from cad.checks.container.wire import (
    CheckedReport,
    FindingWire,
    RequestWire,
    ResultWire,
    StepNotWritten,
    StepWire,
)

CPU_KILL_AFTER_SECONDS = 5


def main() -> None:
    # OCCT prints transfer statistics to fd 1 from C++, so fd 1 is moved aside before OCP loads.
    report_channel = os.dup(1)
    os.dup2(2, 1)
    cpu_seconds = int(sys.argv[1])
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + CPU_KILL_AFTER_SECONDS))
    request = cast(RequestWire, json.loads(sys.argv[2]))
    report = run(request, sys.stdin.buffer.read(), ocp_kernel(), int(sys.argv[3]))
    sys.stdout.flush()
    sys.stderr.flush()
    with os.fdopen(report_channel, "wb") as channel:
        channel.write(json.dumps(report).encode())
    os._exit(0)


def run(request: RequestWire, brep: bytes, kernel: Kernel, report_cap: int) -> CheckedReport:
    shape = kernel.read_brep(brep)
    subject = Subject(kernel, shape, request["density"])
    results = [_run_check(check.ID, check.run, subject) for check in CHECKS]
    room = _step_room(results, report_cap)
    return {"kind": "checked", "results": results, "step": _step(kernel, shape, room)}


def _run_check(
    check_id: str, run_check: Callable[[Subject], FindingWire], subject: Subject
) -> ResultWire:
    try:
        found = run_check(subject)
    except Exception as error:
        found = finding(
            "unknown", f"{check_id} raised {type(error).__name__}: {first_line(str(error))}"
        )
    return {
        "id": check_id,
        "verdict": found["verdict"],
        "measured": found["measured"],
        "reason": found["reason"],
    }


def _step_room(results: list[ResultWire], report_cap: int) -> int:
    empty: CheckedReport = {
        "kind": "checked",
        "results": results,
        "step": {"kind": "written", "base64": ""},
    }
    return _raw_bytes_that_fit_in_base64(report_cap - len(json.dumps(empty).encode()))


def _raw_bytes_that_fit_in_base64(chars: int) -> int:
    return max(chars, 0) // 4 * 3


def _step(kernel: Kernel, shape: Shape | Unreadable, room: int) -> StepWire:
    if isinstance(shape, Unreadable):
        return _missing("no STEP was derived, because the BREP could not be read")
    try:
        written = kernel.step_bytes(shape, room)
    except Exception as error:
        return _missing(f"the STEP writer raised {type(error).__name__}: {first_line(str(error))}")
    if isinstance(written, StepTooLarge):
        return _missing(
            f"the STEP is {written.size} bytes, over the {room} bytes the check report has room for"
        )
    return {"kind": "written", "base64": base64.b64encode(written).decode()}


def _missing(reason: str) -> StepNotWritten:
    return {"kind": "missing", "reason": reason}

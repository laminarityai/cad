import base64
import json
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import cast

from cad.checks.container.calculix import Material, NodalField, NodalLoads, SolveFailed, solve
from cad.checks.container.channel import serve
from cad.checks.container.check import BodyPart, Fem, Subject, finding
from cad.checks.container.inputs import Inputs
from cad.checks.container.kernel import (
    Kernel,
    Shape,
    StepTooLarge,
    Unreadable,
    first_line,
    ocp_kernel,
)
from cad.checks.container.mesher import MeshFailed, TetMesh, tet_mesh
from cad.checks.container.suite import with_requirements
from cad.checks.container.wire import (
    CheckedReport,
    FindingWire,
    RequestWire,
    ResultWire,
    StepNotWritten,
    StepWire,
)


def main() -> None:
    serve(
        lambda args, brep: run(
            cast(RequestWire, json.loads(args[0])), brep, ocp_kernel(), int(args[1])
        )
    )


@dataclass(frozen=True, slots=True)
class BrepFem:
    brep: bytes

    def mesh(self, size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        return tet_mesh(self.brep, size_mm, floor_mm)

    def solve(
        self,
        mesh: TetMesh,
        material: Material,
        fixed: frozenset[int],
        unit_loads: Sequence[NodalLoads],
    ) -> tuple[NodalField, ...] | SolveFailed:
        return solve(mesh, material, fixed, unit_loads)


def run(
    request: RequestWire, stdin: bytes, kernel: Kernel, report_cap: int, fem: Fem | None = None
) -> Iterator[CheckedReport | StepWire]:
    """Yields the results, then the STEP, so the results are sent before the STEP is written."""
    brep, context = _split(stdin, request["context_bytes"], kernel)
    shape = kernel.read_brep(brep)
    engines = BrepFem(brep) if fem is None else fem
    results: list[ResultWire] = []
    for check in with_requirements(request["checks"]):
        reported = {result["id"]: result for result in results}
        cases = tuple(request["load_cases"])
        inputs = Inputs(check.TAKES, request["values"], cases)
        bodies = tuple(
            BodyPart(
                body["name"], tuple(body["solids"]), Inputs(check.TAKES, body["values"], cases)
            )
            for body in request["bodies"]
        )
        subject = Subject(kernel, engines, shape, inputs, reported, context, bodies)
        results.append(_run_check(check.ID, check.run, subject))
    report: CheckedReport = {"kind": "checked", "results": results}
    yield report
    yield _step(kernel, shape, _step_room(report, report_cap))


def _split(
    stdin: bytes, context_bytes: int, kernel: Kernel
) -> tuple[bytes, Shape | Unreadable | None]:
    if context_bytes == 0:
        return stdin, None
    if not 0 < context_bytes <= len(stdin):
        return stdin, Unreadable(f"the host named {context_bytes} context bytes of {len(stdin)}")
    cut = len(stdin) - context_bytes
    return stdin[:cut], kernel.read_brep(stdin[cut:])


def _run_check(
    check_id: str, run_check: Callable[[Subject], FindingWire], subject: Subject
) -> ResultWire:
    try:
        found = run_check(subject)
    except Exception as error:
        found = finding(
            "unknown", f"{check_id} raised {type(error).__name__}: {first_line(str(error))}"
        )
    return {"id": check_id, **found}


def _step_room(report: CheckedReport, report_cap: int) -> int:
    """Each message is a line of JSON, so each costs its newline too."""
    empty: StepWire = {"kind": "written", "base64": ""}
    sent = len(json.dumps(report).encode()) + len(json.dumps(empty).encode()) + 2
    return _raw_bytes_that_fit_in_base64(report_cap - sent)


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

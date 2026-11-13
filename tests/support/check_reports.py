"""Check container reports, as the host reads them, for the report boundary tests."""

import json
from base64 import b64encode
from typing import Any

from cad.sandbox.container import Attended, ContainerState, Job, Ran, TooMuchOutput

STEP = b"ISO-10303-21; fake STEP"
OWN_LIMITS = Job("check", "sha256:analysis", (), b"", wall_seconds=60, memory_mb=1536)
DIMENSIONLESS = "dimensionless"


def measured(name: str, magnitude: float, unit: str) -> dict[str, Any]:
    return {"name": name, "magnitude": magnitude, "unit": unit}


def good_report() -> dict[str, Any]:
    return {
        "kind": "checked",
        "results": [
            {
                "id": "closed_solid",
                "verdict": "pass",
                "measured": [
                    measured("solids", 1, DIMENSIONLESS),
                    measured("free_edges", 0, DIMENSIONLESS),
                    measured("over_used_edges", 0, DIMENSIONLESS),
                    measured("valid", 1, DIMENSIONLESS),
                ],
                "reason": "one valid solid",
            },
            {
                "id": "interference",
                "verdict": "pass",
                "measured": [
                    measured("bodies", 1, DIMENSIONLESS),
                    measured("interfering_pairs", 0, DIMENSIONLESS),
                    measured("max_common_volume", 0, "mm^3"),
                ],
                "reason": "one solid",
            },
            {
                "id": "mass",
                "verdict": "pass",
                "measured": [
                    measured("volume", 1000.0, "mm^3"),
                    measured("center_of_mass:x", 1.0, "mm"),
                    measured("density", 1.24e-6, "kg/mm^3"),
                    measured("mass", 1.24e-3, "kg"),
                ],
                "reason": "1000 mm^3",
            },
            {
                "id": "extents",
                "verdict": "pass",
                "measured": [
                    measured("extent:x", 10.0, "mm"),
                    measured("sorted_extent:smallest", 10.0, "mm"),
                ],
                "reason": "10 mm",
            },
            {
                "id": "holes",
                "verdict": "pass",
                "measured": [
                    measured("hole_count", 0, DIMENSIONLESS),
                    measured("unclassified_openings", 0, DIMENSIONLESS),
                ],
                "reason": "0 round holes",
            },
            {
                "id": "min_wall",
                "verdict": "pass",
                "measured": [measured("min_wall", 2.0, "mm")],
                "reason": "thinnest wall 2 mm",
            },
        ],
        "step": {"kind": "written", "base64": b64encode(STEP).decode()},
    }


def ran(
    report: bytes | TooMuchOutput,
    *,
    killed: bool = False,
    oom: bool = False,
    exit_code: int = 0,
) -> Ran:
    state = ContainerState(Status="exited", ExitCode=exit_code, OOMKilled=oom, Error="")
    return Ran(Attended(killed_at_deadline=killed, report=report, output=""), state)


def lines(report: dict[str, Any]) -> bytes:
    """The results line and the STEP line the container sends for `report`."""
    results = {name: value for name, value in report.items() if name != "step"}
    return b"".join(json.dumps(one).encode() + b"\n" for one in (results, report["step"]))


def sent(report: dict[str, Any]) -> Ran:
    return ran(lines(report))


def with_result(index: int, **changes: Any) -> dict[str, Any]:
    report = good_report()
    report["results"][index].update(changes)
    return report

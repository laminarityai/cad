import base64
from pathlib import Path

import pytest

from cad.geometry.container import coloured_step, export
from cad.sandbox.wire import AreaReport, BodyReport
from tests.support.solids import box, brep_bytes

PAD: list[AreaReport] = [{"name": "rubber pad", "colour": "#1a1a1a", "faces": [5]}]
CAP = 8 * 2**20


def test_a_coloured_step_writer_that_raises_leaves_the_plain_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(brep: bytes, areas: list[AreaReport], bodies: list[BodyReport], cap: int) -> bytes:
        raise RuntimeError("STEPCAFControl_Writer could not transfer the coloured shape")

    def meshes(
        brep: bytes,
        directory: Path,
        chord_mm: float,
        areas: list[AreaReport],
        bodies: list[BodyReport],
    ) -> tuple[bytes, bytes]:
        return b"stl", b"3mf"

    monkeypatch.setattr(coloured_step, "step_bytes", broken)
    monkeypatch.setattr(export, "_meshes", meshes)
    report = export.export(brep_bytes(box(30, 20, 4)), CAP, PAD, [])
    assert report["kind"] == "exported", report
    step = base64.b64decode(report["step"])
    assert step.startswith(b"ISO-10303-21;") and b"MANIFOLD_SOLID_BREP" in step
    assert b"COLOUR_RGB" not in step

import base64
import hashlib
import importlib
import io
import itertools
import re
import tempfile
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Final, Protocol, cast

from cad.checks.container.channel import serve
from cad.checks.container.kernel import StepTooLarge, Unreadable, first_line, ocp_kernel
from cad.geometry.container import coloured_step
from cad.geometry.container.coloured_step import AreaWire
from cad.geometry.container.export_wire import ExportReport

CHORDS_MM: Final = (0.01, 0.05)
ANGULAR_TOLERANCE: Final = 0.1
STL_HEADER_BYTES: Final = 80
THREEMF_MODEL: Final = "3D/3dmodel.model"
THREEMF_UUID: Final = re.compile(r'p:UUID="[^"]*"')
ZIP_EPOCH: Final = (1980, 1, 1, 0, 0, 0)
BASE64_ENVELOPE_BYTES: Final = 1024


class _Mesher(Protocol):
    def add_shape(
        self, shape: object, linear_deflection: float, angular_deflection: float
    ) -> object: ...
    def write(self, file_name: str) -> None: ...


class _Units(Protocol):
    MM: object


class _Build123d(Protocol):
    Unit: _Units
    Mesher: Callable[[object], _Mesher]

    def import_brep(self, file_name: str) -> object: ...


def main() -> None:
    serve(lambda args, brep: iter([export(brep, int(args[0]), coloured_step.parse(args[1]))]))


def export(brep: bytes, report_cap: int, areas: list[AreaWire]) -> ExportReport:
    """STEP from the same writer the checks use, so it is the file they measured, or, when the
    build code coloured areas, the same shape with their colours. Then the binary STL and the
    3MF of one tessellation, in millimetres, with no colour. The mesh gets coarser once if the
    three files would not fit the report."""
    kernel = ocp_kernel()
    shape = kernel.read_brep(brep)
    if isinstance(shape, Unreadable):
        return {"kind": "unreadable", "reason": shape.reason}
    room = max(report_cap - BASE64_ENVELOPE_BYTES, 0) // 4 * 3
    try:
        coloured = coloured_step.step_bytes(brep, areas, room) if areas else None
        step = kernel.step_bytes(shape, room) if coloured is None else coloured
    except Exception as error:
        return {
            "kind": "unreadable",
            "reason": f"the STEP writer raised {type(error).__name__}: {first_line(str(error))}",
        }
    if isinstance(step, StepTooLarge):
        return _too_large(f"the STEP is {step.size} bytes, over the room the export report has")
    try:
        with tempfile.TemporaryDirectory() as directory:
            for chord in CHORDS_MM:
                stl, threemf = _meshes(brep, Path(directory), chord)
                if len(step) + len(stl) + len(threemf) <= room:
                    return {
                        "kind": "exported",
                        "step": _encoded(step),
                        "stl": _encoded(stl),
                        "threemf": _encoded(threemf),
                    }
    except Exception as error:
        return {"kind": "unreadable", "reason": f"{type(error).__name__}: {first_line(str(error))}"}
    return _too_large(f"the mesh at {CHORDS_MM[-1]} mm is over the room the export report has")


def _meshes(brep: bytes, directory: Path, chord_mm: float) -> tuple[bytes, bytes]:
    build123d = cast(_Build123d, importlib.import_module("build123d"))
    (directory / "part.brep").write_bytes(brep)
    mesher = build123d.Mesher(build123d.Unit.MM)
    mesher.add_shape(
        build123d.import_brep(str(directory / "part.brep")), chord_mm, ANGULAR_TOLERANCE
    )
    mesher.write(str(directory / "part.stl"))
    mesher.write(str(directory / "part.3mf"))
    sha256 = hashlib.sha256(brep).hexdigest()
    return _stl_naming((directory / "part.stl").read_bytes(), sha256), _3mf_pinned(
        (directory / "part.3mf").read_bytes(), sha256
    )


def _stl_naming(stl: bytes, brep_sha256: str) -> bytes:
    """An STL has no unit field, so its 80-byte header says millimetres and names the BREP."""
    header = f"units mm; brep {brep_sha256}".encode().ljust(STL_HEADER_BYTES)
    return header + stl[STL_HEADER_BYTES:]


def _3mf_pinned(threemf: bytes, brep_sha256: str) -> bytes:
    """lib3mf draws a random UUID for each object of the model, so one BREP would be written as
    a different file each time. Each UUID becomes one derived from the BREP and its place in the
    model, and the archive is written again with fixed times."""
    names = itertools.count()

    def pinned(_: re.Match[str]) -> str:
        return f'p:UUID="{uuid.uuid5(uuid.NAMESPACE_URL, f"brep:{brep_sha256}:{next(names)}")}"'

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(threemf)) as old, zipfile.ZipFile(out, "w") as new:
        for member in old.infolist():
            data = old.read(member)
            if member.filename == THREEMF_MODEL:
                data = THREEMF_UUID.sub(pinned, data.decode()).encode()
            made = zipfile.ZipInfo(member.filename, ZIP_EPOCH)
            made.compress_type = zipfile.ZIP_DEFLATED
            new.writestr(made, data)
    return out.getvalue()


def _too_large(reason: str) -> ExportReport:
    return {"kind": "too_large", "reason": reason}


def _encoded(data: bytes) -> str:
    return base64.b64encode(data).decode()

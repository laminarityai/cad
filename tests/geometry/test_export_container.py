import hashlib
import re
import struct
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

import pytest

from cad.checks.result import CheckRun, StepStored
from cad.geometry.exports import job, store
from cad.geometry.exports.lane import Exports
from cad.geometry.exports.model import Exported, ExportFailed
from cad.sandbox import image
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.variants import entry
from cad.variants.store import build_variant

pytestmark = pytest.mark.docker

PARTS = Path(__file__).parents[1] / "sandbox/parts"
Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]


@dataclass(frozen=True)
class Plate:
    """The plate's files as the export job wrote them, beside what the checks said."""

    held: entry.Entry
    made: job.Made
    checked: CheckRun

    @property
    def stored_step(self) -> bytes:
        return (self.held.directory / entry.STEP).read_bytes()

    def extents(self) -> list[float]:
        result = self.checked.result("extents")
        return [result.number(f"extent:{axis}", "mm") for axis in "xyz"]


@pytest.fixture(scope="module")
def plate(tmp_path_factory: pytest.TempPathFactory) -> Plate:
    root = tmp_path_factory.mktemp("plate")
    built = build_variant((PARTS / "plate.py").read_text(), root / "variants")
    assert built.outcome == Built(), built.output
    checked = run_checks(built.variant_id, "prusament-pla", root / "variants")
    held = entry.open_entry(root / "variants", built.variant_id, image.image_tag(image.BUILD))
    read = Exports().read(root / "geometry", held, wait_seconds=120)
    assert isinstance(read, Exported), read
    files = {
        suffix: store.path(root / "geometry", held.brep_sha256, suffix).read_bytes()
        for suffix in ("step", "stl", "3mf")
    }
    return Plate(held, job.Made(files["step"], files["stl"], files["3mf"]), checked)


def stl_triangles(data: bytes) -> list[Triangle]:
    (count,) = struct.unpack_from("<I", data, 80)
    assert len(data) == 84 + 50 * count, "not a binary STL"
    found: list[Triangle] = []
    for at in range(84, len(data), 50):
        values = struct.unpack_from("<12f", data, at)
        found.append((values[3:6], values[6:9], values[9:12]))
    return found


def box_of(points: list[Point]) -> list[float]:
    return [max(p[axis] for p in points) - min(p[axis] for p in points) for axis in range(3)]


def welded(triangles: list[Triangle]) -> list[tuple[int, int, int]]:
    index: dict[tuple[int, ...], int] = {}
    out: list[tuple[int, int, int]] = []
    for triangle in triangles:
        ids = [index.setdefault(tuple(round(c * 1e4) for c in p), len(index)) for p in triangle]
        out.append((ids[0], ids[1], ids[2]))
    return out


def test_the_step_is_the_one_the_checks_measured(plate: Plate) -> None:
    assert isinstance(plate.checked.step, StepStored)
    assert plate.made.step == plate.stored_step
    assert hashlib.sha256(plate.made.step).hexdigest() == plate.checked.step.sha256
    assert plate.made.step.startswith(b"ISO-10303-21;")


def test_the_stl_is_a_binary_closed_mesh_the_size_of_the_extents_check(plate: Plate) -> None:
    triangles = stl_triangles(plate.made.stl)
    assert box_of([p for triangle in triangles for p in triangle]) == pytest.approx(
        plate.extents(), abs=1e-3
    )
    edges = Counter(
        frozenset(pair) for a, b, c in welded(triangles) for pair in ((a, b), (b, c), (c, a))
    )
    assert set(edges.values()) == {2}
    assert plate.made.stl[:80].decode().startswith(f"units mm; brep {plate.held.brep_sha256}")


def test_the_3mf_names_millimetres_and_has_the_same_box(plate: Plate, tmp_path: Path) -> None:
    path = tmp_path / "plate.3mf"
    path.write_bytes(plate.made.threemf)
    with zipfile.ZipFile(path) as archive:
        model = archive.read("3D/3dmodel.model").decode()
    assert ElementTree.fromstring(model).get("unit") == "millimeter"
    columns = [
        [float(v) for v in re.findall(rf'<vertex [^>]*\b{axis}="([^"]+)"', model)] for axis in "xyz"
    ]
    assert [max(c) - min(c) for c in columns] == pytest.approx(plate.extents(), abs=1e-3)


def test_the_same_brep_exported_again_gives_the_same_files(plate: Plate) -> None:
    again = job.export(plate.held.brep, plate.held.brep_sha256, ())
    assert again.made == plate.made


COLOURED = """
from build123d import *
plate = Box(30, 20, 4)
plate.color, plate.label = Color(0.5, 0.5, 0.5), "aluminium plate"
top = plate.faces().sort_by(Axis.Z)[-1]
areas = [Compound([top], label="rubber pad", color=Color(0.1, 0.1, 0.1))]
result = plate
"""


def test_the_step_of_a_coloured_variant_carries_each_area_and_the_stl_does_not(
    tmp_path: Path,
) -> None:
    built = build_variant(COLOURED, tmp_path / "variants")
    assert isinstance(built.outcome, Built) and len(built.outcome.areas) == 2, built.output
    held = entry.open_entry(tmp_path / "variants", built.variant_id, image.image_tag(image.BUILD))
    plain = job.export(held.brep, held.brep_sha256, ())
    coloured = job.export(held.brep, "c" * 64, held.areas)
    assert plain.made is not None and coloured.made is not None
    step = coloured.made.step.decode()
    assert step.startswith("ISO-10303-21;") and "2000-01-01T00:00:00" in step
    assert "COLOUR_RGB" not in plain.made.step.decode()
    written = {
        tuple(round(float(value), 3) for value in found.split(","))
        for found in re.findall(r"COLOUR_RGB\('[^']*',([^)]*)\)", step)
    }
    assert written == {(0.502, 0.502, 0.502), (0.102, 0.102, 0.102)}
    assert coloured.made.stl == plain.made.stl
    assert coloured.made == job.export(held.brep, "c" * 64, held.areas).made


def test_a_brep_that_will_not_read_is_a_lasting_failure_with_a_reason(tmp_path: Path) -> None:
    brep = b"not a brep"
    sha = hashlib.sha256(brep).hexdigest()
    held = entry.Entry(entry.VariantId("0123456789abcdef"), tmp_path, brep, sha)
    read = Exports().read(tmp_path / "geometry", held, wait_seconds=120)
    assert isinstance(read, ExportFailed) and read.reason
    assert store.read(tmp_path / "geometry", sha) == read
    assert store.read_file(tmp_path / "geometry", sha, "step") is None

import os
import subprocess
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.checks.container.elastic import Stress
from cad.checks.container.mesher import TetMesh
from cad.checks.container.vectors import Point

type NodalLoads = Mapping[int, Point]
"""Force in N on each loaded node, by node index."""

JOB: Final = "job"
IDS_PER_LINE: Final = 16
REAL_DIGITS: Final = 12
# SPOOLES peaked at 2.7 GB on a 130k-node mesh, over the 2 GB a check gets; this took 0.6 GB.
SOLVER: Final = "ITERATIVE CHOLESKY"
VALUE_WIDTH: Final = 12
VALUES_AT: Final = 13
ONE_THREAD: Final = {
    "OMP_NUM_THREADS": "1",
    "CCX_NPROC_EQUATION_SOLVER": "1",
    "CCX_NPROC_STIFFNESS": "1",
    "CCX_NPROC_RESULTS": "1",
}


@dataclass(frozen=True, slots=True)
class Material:
    elastic_modulus: float
    """MPa, so the deck is in mm, N and MPa."""
    poisson_ratio: float


@dataclass(frozen=True, slots=True)
class NodalField:
    displacement: tuple[Point, ...]
    stress: tuple[Stress, ...]


@dataclass(frozen=True, slots=True)
class SolveFailed:
    reason: str


def solve(
    mesh: TetMesh, material: Material, fixed: frozenset[int], unit_loads: Sequence[NodalLoads]
) -> tuple[NodalField, ...] | SolveFailed:
    """One linear static step per load, with every translation of the `fixed` nodes held."""
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / f"{JOB}.inp").write_text(deck(mesh, material, fixed, unit_loads))
        ran = subprocess.run(
            ["ccx", "-i", JOB],
            cwd=work,
            env={**ONE_THREAD, "PATH": os.environ.get("PATH", ""), "HOME": directory},
            capture_output=True,
            text=True,
            check=False,
        )
        frd = work / f"{JOB}.frd"
        errors = [line.strip() for line in ran.stdout.splitlines() if "*ERROR" in line]
        if ran.returncode != 0 or errors or not frd.is_file():
            said = (errors or ran.stdout.strip().splitlines() or ["no output"])[-1]
            return SolveFailed(f"ccx exited with code {ran.returncode}: {said}")
        return read_frd(frd.read_text(), len(mesh.nodes), len(unit_loads))


def deck(
    mesh: TetMesh, material: Material, fixed: frozenset[int], unit_loads: Sequence[NodalLoads]
) -> str:
    return "\n".join(_deck_lines(mesh, material, fixed, unit_loads)) + "\n"


def _deck_lines(
    mesh: TetMesh, material: Material, fixed: frozenset[int], unit_loads: Sequence[NodalLoads]
) -> Iterator[str]:
    yield "*NODE, NSET=NALL"
    yield from (
        f"{i + 1}, {_real(x)}, {_real(y)}, {_real(z)}" for i, (x, y, z) in enumerate(mesh.nodes)
    )
    yield "*ELEMENT, TYPE=C3D10, ELSET=EALL"
    yield from (
        f"{e + 1}, " + ", ".join(str(i + 1) for i in tet) for e, tet in enumerate(mesh.tets)
    )
    ids = sorted(i + 1 for i in fixed)
    yield "*NSET, NSET=FIXED"
    yield from (
        ", ".join(map(str, ids[start : start + IDS_PER_LINE]))
        for start in range(0, len(ids), IDS_PER_LINE)
    )
    yield "*BOUNDARY"
    yield "FIXED, 1, 3"
    yield "*MATERIAL, NAME=SOLID"
    yield "*ELASTIC"
    yield f"{_real(material.elastic_modulus)}, {_real(material.poisson_ratio)}"
    yield "*SOLID SECTION, ELSET=EALL, MATERIAL=SOLID"
    for loads in unit_loads:
        yield "*STEP"
        yield f"*STATIC, SOLVER={SOLVER}"
        yield "*CLOAD, OP=NEW"
        for i, force in sorted(loads.items()):
            yield from (
                f"{i + 1}, {dof}, {_real(value)}" for dof, value in enumerate(force, 1) if value
            )
        yield "*NODE FILE"
        yield "U"
        yield "*EL FILE"
        yield "S"
        yield "*END STEP"


def _real(value: float) -> str:
    """CalculiX reads at most 20 characters per field, which `repr` can exceed."""
    return f"{value:.{REAL_DIGITS}e}"


def read_frd(text: str, nodes: int, steps: int) -> tuple[NodalField, ...] | SolveFailed:
    blocks: dict[str, list[dict[int, tuple[float, ...]]]] = {"DISP": [], "STRESS": []}
    current: dict[int, tuple[float, ...]] | None = None
    try:
        for line in text.splitlines():
            if line.startswith(" -4"):
                name = line.split()[1]
                current = {} if name in blocks else None
                if current is not None:
                    blocks[name].append(current)
            elif line.startswith(" -1") and current is not None:
                current[int(line[3:VALUES_AT])] = _values(line[VALUES_AT:])
            elif line.startswith(" -3"):
                current = None
    except ValueError as error:
        return SolveFailed(f"the .frd file has a malformed line: {error}")
    found = {name: len(per_step) for name, per_step in blocks.items()}
    if found != {"DISP": steps, "STRESS": steps}:
        return SolveFailed(f"the .frd file holds {found} result blocks, not {steps} of each")
    fields: list[NodalField] = []
    for displaced, stressed in zip(blocks["DISP"], blocks["STRESS"], strict=True):
        ids = range(1, nodes + 1)
        if any(i not in displaced or i not in stressed for i in ids):
            return SolveFailed("the .frd file leaves out some nodes")
        displacement = tuple(_point(displaced[i]) for i in ids)
        stress = tuple(_stress(stressed[i]) for i in ids)
        fields.append(NodalField(displacement, stress))
    return tuple(fields)


def _values(fixed_width: str) -> tuple[float, ...]:
    return tuple(
        float(fixed_width[start : start + VALUE_WIDTH])
        for start in range(0, len(fixed_width.rstrip()), VALUE_WIDTH)
    )


def _point(values: tuple[float, ...]) -> Point:
    x, y, z = values[:3]
    return (x, y, z)


def _stress(values: tuple[float, ...]) -> Stress:
    xx, yy, zz, xy, yz, zx = values[:6]
    return (xx, yy, zz, xy, yz, zx)

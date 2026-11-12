import math
from dataclasses import dataclass
from typing import Literal

from cad.checks.container.anchors import Bore, FarFrom, Plane, Region
from cad.checks.container.calculix import Material
from cad.checks.container.vectors import Point

type Measure = Literal["max_displacement", "max_von_mises"]

E = 200_000.0
STEEL = Material(E, 0.3)
NO_POISSON = Material(E, 0.0)
SHEAR_COEFFICIENT = 5 / 6
Z = (0.0, 0.0, 1.0)
ORIGIN = (0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class PlateLoadPatch:
    center: Point
    normal: Point
    radius: float


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    code: str
    material: Material
    fixed: Region
    loaded: Region | FarFrom | PlateLoadPatch
    force: Point
    measure: Measure
    expected: float
    tolerance: float
    reference: str


def box(length: float, width: float, height: float) -> str:
    return (
        "from build123d import Align, Box\n"
        f"result = Box({length}, {width}, {height}, align=(Align.MIN, Align.MIN, Align.MIN))\n"
    )


def end(x: float, width: float, height: float, outward: float) -> Region:
    return Region((Plane((x, 0.0, 0.0), (outward, 0.0, 0.0)),), (x, width / 2, height / 2))


def far_along_x(support: Region) -> FarFrom:
    return FarFrom(support.centroid, (1.0, 0.0, 0.0))


BAR_L, BAR_A, BAR_P = 100.0, 10.0 * 10.0, 1000.0
BEAM_L, BEAM_B, BEAM_H, BEAM_P = 200.0, 10.0, 5.0, 10.0
BEAM_I = BEAM_B * BEAM_H**3 / 12
FILLET_L, FILLET_R = 100.0, 1.0
PLATE_A, PLATE_T, PATCH_R, PLATE_P = 50.0, 2.5, 1.0, 10.0
PLATE_D = E * PLATE_T**3 / (12 * (1 - STEEL.poisson_ratio**2))
HOLE_W, HOLE_T, HOLE_D, HOLE_P = 40.0, 4.0, 8.0, 1000.0


def timoshenko_tip(
    material: Material,
    length: float = BEAM_L,
    second_moment: float = BEAM_I,
    area: float = BEAM_B * BEAM_H,
) -> float:
    shear_modulus = material.elastic_modulus / (2 * (1 + material.poisson_ratio))
    bending = BEAM_P * length**3 / (3 * material.elastic_modulus * second_moment)
    return bending + BEAM_P * length / (SHEAR_COEFFICIENT * shear_modulus * area)


def rounded_second_moment(width: float, height: float, radius: float) -> float:
    """The rectangle's I about its width axis, less at each corner an r by r square less the
    quarter disc the fillet keeps."""
    inner = height / 2 - radius
    square = radius * ((height / 2) ** 3 - inner**3) / 3
    disc = math.pi * radius**2 * inner**2 / 4 + 2 * inner * radius**3 / 3 + math.pi * radius**4 / 16
    return width * height**3 / 12 - 4 * (square - disc)


FILLETED_BEAM_CODE = f"""\
from build123d import Align, Axis, Box, fillet

result = Box({FILLET_L}, {BEAM_B}, {BEAM_H}, align=(Align.MIN, Align.MIN, Align.MIN))
result = fillet(result.edges().filter_by(Axis.X), {FILLET_R})
"""


PLATE_CODE = f"""\
from build123d import Align, Cylinder, Shape
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse

up = (Align.CENTER, Align.CENTER, Align.MIN)
patch = Cylinder({PATCH_R}, {PLATE_T}, align=up)
rest = Cylinder({PLATE_A}, {PLATE_T}, align=up) - patch
result = Shape.cast(BRepAlgoAPI_Fuse(patch.wrapped, rest.wrapped).Shape())
"""

HOLE_CODE = f"""\
from build123d import Align, Box, Cylinder, Pos

result = Box(200, {HOLE_W}, {HOLE_T}, align=(Align.MIN, Align.MIN, Align.MIN)) - Pos(
    100, {HOLE_W / 2}, {HOLE_T / 2}
) * Cylinder({HOLE_D / 2}, {HOLE_T})
"""

CASES: tuple[Case, ...] = (
    Case(
        name="axial bar",
        code=box(BAR_L, 10, 10),
        material=STEEL,
        fixed=end(0.0, 10, 10, -1),
        loaded=far_along_x(end(0.0, 10, 10, -1)),
        force=(BAR_P, 0.0, 0.0),
        measure="max_displacement",
        expected=BAR_P * BAR_L / (E * BAR_A),
        tolerance=0.02,
        reference="delta = PL/(EA)",
    ),
    Case(
        name="cantilever tip",
        code=box(BEAM_L, BEAM_B, BEAM_H),
        material=STEEL,
        fixed=end(0.0, BEAM_B, BEAM_H, -1),
        loaded=far_along_x(end(0.0, BEAM_B, BEAM_H, -1)),
        force=(0.0, 0.0, -BEAM_P),
        measure="max_displacement",
        expected=timoshenko_tip(STEEL),
        tolerance=0.03,
        reference="delta = PL^3/(3EI) + PL/(kGA), Timoshenko & Gere",
    ),
    Case(
        name="filleted cantilever tip",
        code=FILLETED_BEAM_CODE,
        material=STEEL,
        fixed=end(0.0, BEAM_B, BEAM_H, -1),
        loaded=far_along_x(end(0.0, BEAM_B, BEAM_H, -1)),
        force=(0.0, 0.0, -BEAM_P),
        measure="max_displacement",
        expected=timoshenko_tip(
            STEEL,
            FILLET_L,
            rounded_second_moment(BEAM_B, BEAM_H, FILLET_R),
            BEAM_B * BEAM_H - (4 - math.pi) * FILLET_R**2,
        ),
        tolerance=0.03,
        reference="a 100 mm cantilever with its long edges rounded: I less each corner's fillet",
    ),
    Case(
        name="cantilever root stress",
        code=box(BEAM_L, BEAM_B, BEAM_H),
        material=NO_POISSON,
        fixed=end(0.0, BEAM_B, BEAM_H, -1),
        loaded=far_along_x(end(0.0, BEAM_B, BEAM_H, -1)),
        force=(0.0, 0.0, -BEAM_P),
        measure="max_von_mises",
        expected=BEAM_P * BEAM_L * (BEAM_H / 2) / BEAM_I,
        tolerance=0.05,
        reference="sigma = PLc/I",
    ),
    Case(
        name="clamped circular plate",
        code=PLATE_CODE,
        material=STEEL,
        fixed=Region((Bore(ORIGIN, Z, PLATE_A, 0.0, PLATE_T),), (0.0, 0.0, PLATE_T / 2)),
        loaded=PlateLoadPatch((0.0, 0.0, PLATE_T), Z, PATCH_R),
        force=(0.0, 0.0, -PLATE_P),
        measure="max_displacement",
        expected=PLATE_P * PLATE_A**2 / (16 * math.pi * PLATE_D),
        tolerance=0.05,
        reference="w = Pa^2/(16 pi D), Roark Table 11.2",
    ),
    Case(
        name="plate with hole",
        code=HOLE_CODE,
        material=NO_POISSON,
        fixed=end(0.0, HOLE_W, HOLE_T, -1),
        loaded=far_along_x(end(0.0, HOLE_W, HOLE_T, -1)),
        force=(HOLE_P, 0.0, 0.0),
        measure="max_von_mises",
        expected=(2 + (1 - HOLE_D / HOLE_W) ** 3) * HOLE_P / ((HOLE_W - HOLE_D) * HOLE_T),
        tolerance=0.07,
        reference="sigma = Kt P/((W-d)t), Kt = 2 + (1-d/W)^3, Heywood via Peterson",
    ),
)

BY_NAME = {case.name: case for case in CASES}

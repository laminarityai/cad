import math
from dataclasses import dataclass
from typing import Literal

from cad.checks.container.calculix import Material
from cad.checks.container.regions import Bore, Disc, FarFrom, Plane, Region
from cad.checks.container.vectors import Point, scale, sub, unit

type Measure = Literal["max_displacement", "max_von_mises"]

E = 200_000.0
STEEL = Material(E, 0.3)
NO_POISSON = Material(E, 0.0)
SHEAR_COEFFICIENT = 5 / 6
Z = (0.0, 0.0, 1.0)
ORIGIN = (0.0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    code: str
    material: Material
    fixed: Region
    loaded: Region | FarFrom
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


def pressed_plate_tip(material: Material) -> float:
    """The tip deflection of a cantilever loaded at half its length."""
    length, at = SHELF_X, SHELF_X / 2
    second_moment, area = SHELF_Y * SHELF_T**3 / 12, SHELF_Y * SHELF_T
    shear_modulus = material.elastic_modulus / (2 * (1 + material.poisson_ratio))
    bending = SHELF_P * at**2 * (3 * length - at) / (6 * material.elastic_modulus * second_moment)
    return bending + SHELF_P * at / (SHEAR_COEFFICIENT * shear_modulus * area)


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

PLATE_X, PLATE_Y, PLATE_Z = 10.0, 30.0, 40.0
PLATE_BELOW = 30.0
PLATED_BEAM_CODE = f"""\
from build123d import Align, Box, Pos

low = (Align.MIN, Align.MIN, Align.MIN)
plate = Pos(-{PLATE_X}, -{(PLATE_Y - BEAM_B) / 2}, -{PLATE_BELOW}) * Box(
    {PLATE_X}, {PLATE_Y}, {PLATE_Z}, align=low
)
result = plate + Box({BEAM_L}, {BEAM_B}, {BEAM_H}, align=low)
"""
PLATE_BACK = Region(
    (Plane((-PLATE_X, 0.0, 0.0), (-1.0, 0.0, 0.0)),),
    (-PLATE_X, BEAM_B / 2, PLATE_Z / 2 - PLATE_BELOW),
)
ARM_TIP = Region((Plane((BEAM_L, 0.0, 0.0), (1.0, 0.0, 0.0)),), (BEAM_L, BEAM_B / 2, BEAM_H / 2))

SHELF_X, SHELF_Y, SHELF_T, SHELF_P = 160.0, 40.0, 6.0, 10.0
"""A plate held at its end x = 0 and pressed into the middle of its top."""
SHELF_ROOT = Region((Plane(ORIGIN, (-1.0, 0.0, 0.0)),), (0.0, SHELF_Y / 2, SHELF_T / 2))
SHELF_TOP = (SHELF_X / 2, SHELF_Y / 2, SHELF_T)
SHELF_MIDDLE = Region((Disc(SHELF_TOP, Z, 0.1 * math.sqrt(SHELF_X * SHELF_Y)),), SHELF_TOP)

C_SIDE, C_DEPTH, C_T, C_P = 80.0, 20.0, 6.0, 100.0
"""A C frame open toward +x, its back and jaws C_T thick, held by its lower jaw's inner face."""
C_FRAME_CODE = f"""\
from build123d import Align, Box, Pos

low = (Align.MIN, Align.MIN, Align.MIN)
gap = Pos({C_T}, -1, {C_T}) * Box({C_SIDE}, {C_DEPTH + 2}, {C_SIDE - 2 * C_T}, align=low)
result = Box({C_SIDE}, {C_DEPTH}, {C_SIDE}, align=low) - gap
"""
C_LOWER = Region((Plane((0.0, 0.0, C_T), Z),), ((C_SIDE + C_T) / 2, C_DEPTH / 2, C_T))
C_UPPER = Region(
    (Plane((0.0, 0.0, C_SIDE - C_T), (0.0, 0.0, -1.0)),),
    ((C_SIDE + C_T) / 2, C_DEPTH / 2, C_SIDE - C_T),
)


def c_frame_tip(material: Material) -> float:
    """The jaw tip's displacement on the centrelines: the back, of length h, under the constant
    moment of the jaw's load about it, plus the jaw as a cantilever from the back under a uniform
    load from s = a to L, by Castigliano, with the jaw's shear and the back's stretch."""
    e, g = material.elastic_modulus, material.elastic_modulus / (2 * (1 + material.poisson_ratio))
    ei, area = e * C_DEPTH * C_T**3 / 12, C_DEPTH * C_T
    h, a, length = C_SIDE - C_T, C_T / 2, C_SIDE - C_T / 2
    arm = (length + a) / 2
    jaw = arm * length * a - (arm + length) * a**2 / 2 + a**3 / 3 + (length - a) ** 3 / 8
    rise = C_P * (arm * h * length + jaw) / ei + C_P * arm / (SHEAR_COEFFICIENT * g * area)
    rise += C_P * h / (e * area)
    sway = C_P * arm * h**2 / (2 * ei)
    return math.hypot(rise, sway)


HOOK_B, HOOK_W, HOOK_RI, HOOK_SHANK, HOOK_HOLE, HOOK_P = 10.0, 10.0, 12.0, 80.0, 4.0, 100.0
"""A J hook: a shank x 0 to HOOK_W wide held by 2 holes near its top, and a half ring below z = 0
around the line x = HOOK_RO, y = HOOK_B / 2."""
HOOK_RO = HOOK_RI + HOOK_W
HOOK_HOLES = (60.0, 74.0)
HOOK_CODE = f"""\
from build123d import Align, Box, Cylinder, Pos, Rot

low = (Align.MIN, Align.MIN, Align.MIN)
ring = Pos({HOOK_RO}, {HOOK_B / 2}, 0) * Rot(90, 0, 0) * (
    Cylinder({HOOK_RO}, {HOOK_B}) - Cylinder({HOOK_RI}, {HOOK_B})
)
ring = ring & Pos(0, 0, -{HOOK_RO}) * Box({2 * HOOK_RO}, {HOOK_B}, {HOOK_RO}, align=low)
result = Box({HOOK_W}, {HOOK_B}, {HOOK_SHANK}, align=low) + ring
for z in {HOOK_HOLES}:
    result -= Pos({HOOK_W / 2}, {HOOK_B / 2}, z) * Rot(90, 0, 0) * Cylinder({HOOK_HOLE / 2}, 30)
"""
HOOK_BORES = Region(
    tuple(
        Bore((HOOK_W / 2, 0.0, z), (0.0, 1.0, 0.0), HOOK_HOLE / 2, 0.0, HOOK_B) for z in HOOK_HOLES
    ),
    (HOOK_W / 2, HOOK_B / 2, sum(HOOK_HOLES) / 2),
)
HOOK_CURL_CENTROID = (HOOK_RO, HOOK_B / 2, -2 * HOOK_RI / math.pi)
HOOK_CURL = Region(
    (Bore((HOOK_RO, 0.0, 0.0), (0.0, 1.0, 0.0), HOOK_RI, 0.0, HOOK_B),), HOOK_CURL_CENTROID
)
HOOK_AWAY = unit(sub(HOOK_CURL_CENTROID, HOOK_BORES.centroid))


def hook_inner_stress() -> float:
    """Winkler-Bach at the section where the curl leaves the shank, z = 0: the load's resultant
    acts at the curl's centroid, so the section carries its moment about the section's centroid
    and the normal force, and the inner fibre at HOOK_RI takes the most."""
    mean = (HOOK_RI + HOOK_RO) / 2
    neutral = HOOK_W / math.log(HOOK_RO / HOOK_RI)
    area, shift = HOOK_W * HOOK_B, mean - neutral
    lever = sub(HOOK_CURL_CENTROID, (HOOK_RO - mean, HOOK_B / 2, 0.0))
    fx, fz = HOOK_P * HOOK_AWAY[0], HOOK_P * HOOK_AWAY[2]
    moment = lever[2] * fx - lever[0] * fz
    return -fz / area + moment * (neutral - HOOK_RI) / (area * shift * HOOK_RI)


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
        name="cantilever on a mounting plate",
        code=PLATED_BEAM_CODE,
        material=STEEL,
        fixed=PLATE_BACK,
        loaded=ARM_TIP,
        force=(0.0, 0.0, -BEAM_P),
        measure="max_displacement",
        expected=timoshenko_tip(STEEL),
        tolerance=0.03,
        reference=(
            "the arm's delta = PL^3/(3EI) + PL/(kGA); the plate's root compliance measured +1.7%"
        ),
    ),
    Case(
        name="clamped circular plate",
        code=PLATE_CODE,
        material=STEEL,
        fixed=Region((Bore(ORIGIN, Z, PLATE_A, 0.0, PLATE_T),), (0.0, 0.0, PLATE_T / 2)),
        loaded=Region((Disc((0.0, 0.0, PLATE_T), Z, PATCH_R),), (0.0, 0.0, PLATE_T)),
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
    Case(
        name="plate pressed in the middle",
        code=box(SHELF_X, SHELF_Y, SHELF_T),
        material=NO_POISSON,
        fixed=SHELF_ROOT,
        loaded=SHELF_MIDDLE,
        force=(0.0, 0.0, -SHELF_P),
        measure="max_displacement",
        expected=pressed_plate_tip(NO_POISSON),
        tolerance=0.03,
        reference=(
            "FlatEnd, OnLargestFlat(middle), Into: tip delta = Pa^2(3L-a)/(6EI) + Pa/(kGA) "
            "with a = L/2, Timoshenko & Gere"
        ),
    ),
    Case(
        name="clamp pried apart",
        code=C_FRAME_CODE,
        material=STEEL,
        fixed=C_LOWER,
        loaded=C_UPPER,
        force=(0.0, 0.0, C_P),
        measure="max_displacement",
        expected=c_frame_tip(STEEL),
        tolerance=0.03,
        reference="Facing, OnOpposite, Into: the back's moment and the jaw's bending, Castigliano",
    ),
    Case(
        name="hook pulled from its curl",
        code=HOOK_CODE,
        material=NO_POISSON,
        fixed=HOOK_BORES,
        loaded=HOOK_CURL,
        force=scale(HOOK_AWAY, HOOK_P),
        measure="max_von_mises",
        expected=hook_inner_stress(),
        tolerance=0.05,
        reference="Holes(2), OnFarthest(inner curve), Away: Winkler-Bach at the curl's root",
    ),
)

BY_NAME = {case.name: case for case in CASES}

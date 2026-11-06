"""Parameterized build123d builders for every part the starting models use.

Called with default arguments, each builder reproduces its part in the starting models
exactly, and validate_grader.py checks that. A reference changes only the arguments its
brief changes.
"""

import math

from build123d import (
    Axis,
    Box,
    Cylinder,
    GeomType,
    Part,
    Polyline,
    Pos,
    RectangleRounded,
    RegularPolygon,
    Rot,
    SlotCenterToCenter,
    chamfer,
    extrude,
    fillet,
    make_face,
)

Points = tuple[tuple[float, float], ...]
PLATE_HOLES: Points = ((42, 17), (-42, 17), (42, -17), (-42, -17))
BLOCK_HOLES: Points = ((15, 15), (-15, -15))
ARM_POCKETS = (62.5, 125.0, 187.5)


def plate(
    holes: Points = PLATE_HOLES, center_hole_r: float = 0, corner_r: float = 0
) -> Part:
    part = Box(100, 50, 6)
    if corner_r:
        part = fillet(part.edges().filter_by(Axis.Z), corner_r)
    for x, y in holes:
        part -= Pos(x, y, 0) * Cylinder(2.55, 20)
    if center_hole_r:
        part -= Cylinder(center_hole_r, 20)
    return part


def l_bracket(base_length: float = 40, wall_hole_r: float = 2.55, inside_r: float = 0) -> Part:
    """Outside corner on the origin, base along +X, wall along +Z, 30 mm wide along +Y."""
    part = Pos(base_length / 2, 15, 1.5) * Box(base_length, 30, 3) + Pos(1.5, 15, 20) * Box(
        3, 30, 40
    )
    if inside_r:
        corner = part.edges().filter_by(Axis.Y).filter_by(
            lambda e: abs(e.center().X - 3) < 1e-6 and abs(e.center().Z - 3) < 1e-6
        )
        part = fillet(corner, inside_r)
    for d in (12, 30):
        part -= Pos(d, 15, 0) * Cylinder(2.55, 20)
        part -= Pos(0, 15, d) * Rot(0, 90, 0) * Cylinder(wall_hole_r, 20)
    return part


def motor_plate(bolt_circle_r: float = 25.4, counterbore: bool = False, chamfer_top: float = 0) -> Part:
    part = Box(60, 60, 6)
    if chamfer_top:
        part = chamfer(part.edges().group_by(Axis.Z)[-1], chamfer_top)
    part -= Cylinder(11, 20)
    if counterbore:
        part -= Pos(0, 0, 2) * Cylinder(15, 2)
    for a in (45, 135, 225, 315):
        x, y = bolt_circle_r * math.cos(math.radians(a)), bolt_circle_r * math.sin(math.radians(a))
        part -= Pos(x, y, 0) * Cylinder(1.6, 20)
    return part


def involute_outline(teeth: int = 24, module: float = 2.0, steps: int = 40) -> list[tuple[float, float]]:
    """Closed outline of a standard 20 degree involute spur gear, a tooth centered on +X."""
    pressure = math.radians(20)
    pitch_r = teeth * module / 2
    tip_r, root_r = pitch_r + module, pitch_r - 1.25 * module
    base_r = pitch_r * math.cos(pressure)

    def inv(a: float) -> float:
        return math.tan(a) - a

    half = math.pi / (2 * teeth) + inv(pressure)
    flank: list[tuple[float, float]] = [(root_r, half)] if root_r < base_r else []
    start = max(base_r, root_r)
    for i in range(steps + 1):
        r = start + (tip_r - start) * i / steps
        flank.append((r, half - inv(math.acos(min(1.0, base_r / r)))))
    points: list[tuple[float, float]] = []
    for k in range(teeth):
        c = 2 * math.pi * k / teeth
        points += [(r * math.cos(c - a), r * math.sin(c - a)) for r, a in flank]
        points += [(r * math.cos(c + a), r * math.sin(c + a)) for r, a in reversed(flank)]
    return points


def spur_gear(bore_r: float = 4, hub: bool = False, keyway: bool = False) -> Part:
    """24 teeth, module 2, 10 mm thick from Z = 0 to Z = 10."""
    part = extrude(make_face(Polyline(*involute_outline(), close=True)), 10)
    if hub:
        part += Pos(0, 0, 12.5) * Cylinder(10, 5)
    part -= Cylinder(bore_r, 40)
    if keyway:
        part -= Pos(0, 2.75, 5) * Box(3, 5.5, 40)
    return part


def hex_spacer(length: float = 10, outer_r: float = 12.5, chamfer_outer: float = 0) -> Part:
    part = Cylinder(outer_r, length)
    if chamfer_outer:
        part = chamfer(part.edges().filter_by(GeomType.CIRCLE), chamfer_outer)
    return part - extrude(RegularPolygon(12.7 / math.sqrt(3), 6), 20, both=True)


def shaft_collar(length: float = 10, chamfer_bore: float = 0, slot: bool = False) -> Part:
    """Tube from Z = -5 upward, with a radial screw hole from +X at Z = 0."""
    part = Pos(0, 0, length / 2 - 5) * Cylinder(12.5, length) - Cylinder(6.35, 60)
    if chamfer_bore:
        bore_edges = part.edges().filter_by(GeomType.CIRCLE).filter_by(
            lambda e: abs(e.radius - 6.35) < 1e-6
        )
        part = chamfer(bore_edges, chamfer_bore)
    part -= Pos(9.5, 0, 0) * Rot(0, 90, 0) * Cylinder(1.65, 7)
    if slot:
        part -= Pos(-9.5, 0, 0) * Box(7, 1, 60)
    return part


def gusset(thickness: float = 4, hole_r: float = 10, extra_holes: Points = ()) -> Part:
    part = extrude(make_face(Polyline((0, 0), (50, 0), (0, 50), close=True)), thickness)
    part = fillet(part.edges().filter_by(Axis.Z), 3)
    part -= Pos(50 / 3, 50 / 3, 0) * Cylinder(hole_r, 20)
    for x, y in extra_holes:
        part -= Pos(x, y, 0) * Cylinder(2, 20)
    return part


def u_bracket(
    height: float = 30, hole_z: float = 20, base_holes: tuple[float, ...] = (), inside_r: float = 2
) -> Part:
    """Base on Z = 0, walls at X = -20..-18 and 18..20, 50 mm deep along Y."""
    part = Pos(0, 0, 1) * Box(40, 50, 2)
    for side in (-1, 1):
        part += Pos(side * 19, 0, height / 2) * Box(2, 50, height)
    if inside_r:
        inside = part.edges().filter_by(Axis.Y).filter_by(
            lambda e: abs(e.center().Z - 2) < 1e-6 and abs(abs(e.center().X) - 18) < 1e-6
        )
        part = fillet(inside, inside_r)
    part -= Pos(0, 0, hole_z) * Rot(0, 90, 0) * Cylinder(3, 60)
    for y in base_holes:
        part -= Pos(0, y, 0) * Cylinder(2, 20)
    return part


def bearing_block(pocket_depth: float = 8, holes: Points = BLOCK_HOLES, corner_r: float = 0) -> Part:
    """40 x 40 mm, from Z = 0 to Z = 20, pocket in the top face."""
    part = Pos(0, 0, 10) * Box(40, 40, 20)
    if corner_r:
        part = fillet(part.edges().filter_by(Axis.Z), corner_r)
    part -= Pos(0, 0, 20 - pocket_depth / 2) * Cylinder(14, pocket_depth)
    part -= Cylinder(6.35, 60)
    for x, y in holes:
        part -= Pos(x, y, 0) * Cylinder(2.55, 60)
    return part


def arm(bore_r: float = 14, pockets: tuple[float, ...] = ARM_POCKETS, bore_spacing: float = 250) -> Part:
    """6 mm thick from Z = 0, first bore at X = -125, pockets measured from it."""
    first = -125
    slot = Pos(first + bore_spacing / 2, 0, 0) * SlotCenterToCenter(bore_spacing, 40)
    part = extrude(slot, 6)
    for x in (first, first + bore_spacing):
        part -= Pos(x, 0, 0) * Cylinder(bore_r, 30)
    for d in pockets:
        part -= Pos(first + d, 0, 3) * extrude(RectangleRounded(30, 20, 3), 20, both=True)
    return part


def small_plate() -> Part:
    """60 x 60 x 4 mm, centered, with 3.2 mm holes at (+-25, +-25)."""
    part = Box(60, 60, 4)
    for x in (-25, 25):
        for y in (-25, 25):
            part -= Pos(x, y, 0) * Cylinder(1.6, 20)
    return part


def tube(outer_r: float, inner_r: float, length: float) -> Part:
    """Centered on the origin, axis along Z."""
    return Cylinder(outer_r, length) - Cylinder(inner_r, length * 3)


def small_gusset() -> Part:
    """Right triangle with 30 mm legs along +X and +Y, 3 mm thick from Z = 0."""
    return extrude(make_face(Polyline((0, 0), (30, 0), (0, 30), close=True)), 3)

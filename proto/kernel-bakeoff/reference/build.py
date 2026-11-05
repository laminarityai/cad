import math
from pathlib import Path

from build123d import (
    Axis, Box, Circle, Cylinder, Locations, Plane, Polyline, Pos, Rot,
    RegularPolygon, Rectangle, RectangleRounded, SlotCenterToCenter,
    export_step, extrude, fillet, make_face,
)

OUT = Path(__file__).parent


def through_holes(part, radius, depth, points):
    for x, y in points:
        part -= Pos(x, y, 0) * Cylinder(radius, depth * 3)
    return part


def plate():
    p = Box(100, 50, 6)
    return through_holes(p, 2.55, 6, [(sx * 42, sy * 17) for sx in (-1, 1) for sy in (-1, 1)])


def l_bracket():
    # Outside corner at the origin, legs along +X and +Z, width along Y.
    base = Pos(20, 15, 1.5) * Box(40, 30, 3)
    wall = Pos(1.5, 15, 20) * Box(3, 30, 40)
    p = base + wall
    for d in (12, 30):
        p -= Pos(d, 15, 0) * Cylinder(2.55, 20)
        p -= Pos(0, 15, d) * Rot(0, 90, 0) * Cylinder(2.55, 20)
    return p


def motor_plate():
    p = Box(60, 60, 6) - Cylinder(11, 20)
    r = 25.4
    pts = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
    return through_holes(p, 1.6, 6, pts)


def involute_gear_outline(z=24, m=2.0, pa_deg=20.0, n=40):
    pa = math.radians(pa_deg)
    rp, ra, rf = z * m / 2, z * m / 2 + m, z * m / 2 - 1.25 * m
    rb = rp * math.cos(pa)
    inv = lambda a: math.tan(a) - a
    half_pitch_thick = math.pi / (2 * z)
    flank = []  # (r, angle from tooth centerline) for one flank, root to tip
    start = max(rb, rf)
    if rf < rb:
        flank.append((rf, half_pitch_thick + inv(pa)))
    for i in range(n + 1):
        r = start + (ra - start) * i / n
        a_r = math.acos(min(1.0, rb / r))
        flank.append((r, half_pitch_thick + inv(pa) - inv(a_r)))
    pts = []
    for k in range(z):
        c = 2 * math.pi * k / z
        # leading flank (negative side) root -> tip, then trailing flank tip -> root
        for r, a in flank:
            pts.append((r * math.cos(c - a), r * math.sin(c - a)))
        for r, a in reversed(flank):
            pts.append((r * math.cos(c + a), r * math.sin(c + a)))
    return pts


def spur_gear():
    pts = involute_gear_outline()
    face = make_face(Polyline(*pts, close=True))
    return extrude(face, 10) - Cylinder(4, 40)


def hex_spacer():
    # RegularPolygon radius is circumradius; across-flats 12.7 -> R = 12.7 / sqrt(3)
    hex_face = RegularPolygon(12.7 / math.sqrt(3), 6)
    return Cylinder(12.5, 10) - extrude(hex_face, 20, both=True)


def shaft_collar():
    p = Cylinder(12.5, 10) - Cylinder(6.35, 20)
    # Radial hole from +X outside into the bore only.
    return p - Pos(9.5, 0, 0) * Rot(0, 90, 0) * Cylinder(1.65, 7)


def gusset():
    tri = make_face(Polyline((0, 0), (50, 0), (0, 50), close=True))
    p = extrude(tri, 4)
    p = fillet(p.edges().filter_by(Axis.Z), 3)
    return p - Pos(50 / 3, 50 / 3, 0) * Cylinder(10, 20)


def u_bracket():
    # X width, Z height, Y depth.
    base = Pos(0, 0, 1) * Box(40, 50, 2)
    walls = [Pos(sx * 19, 0, 15) * Box(2, 50, 30) for sx in (-1, 1)]
    p = base + walls[0] + walls[1]
    inside = p.edges().filter_by(Axis.Y).filter_by(
        lambda e: abs(e.center().Z - 2) < 1e-6 and abs(abs(e.center().X) - 18) < 1e-6
    )
    p = fillet(inside, 2)
    return p - Pos(0, 0, 20) * Rot(0, 90, 0) * Cylinder(3, 60)


def bearing_block():
    p = Pos(0, 0, 10) * Box(40, 40, 20)
    p -= Pos(0, 0, 20 - 4) * Cylinder(14, 8)
    p -= Cylinder(6.35, 60)
    return through_holes(p, 2.55, 20, [(15, 15), (-15, -15)])


def arm():
    p = extrude(SlotCenterToCenter(250, 40), 6)
    for x in (-125, 125):
        p -= Pos(x, 0, 0) * Cylinder(14, 30)
    for d in (62.5, 125, 187.5):
        p -= Pos(-125 + d, 0, 3) * extrude(RectangleRounded(30, 20, 3), 20, both=True)
    return p


PARTS = {
    "plate": plate, "l_bracket": l_bracket, "motor_plate": motor_plate,
    "spur_gear": spur_gear, "hex_spacer": hex_spacer, "shaft_collar": shaft_collar,
    "gusset": gusset, "u_bracket": u_bracket, "bearing_block": bearing_block, "arm": arm,
}

if __name__ == "__main__":
    for name, fn in PARTS.items():
        part = fn()
        export_step(part, str(OUT / f"{name}.step"))
        bb = part.bounding_box()
        print(f"{name:14s} vol={part.volume:10.2f} bbox={bb.size.X:.2f}x{bb.size.Y:.2f}x{bb.size.Z:.2f} solids={len(part.solids())}")

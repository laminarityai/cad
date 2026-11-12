"""The 20 corpus parts of the fea load anchors and described-loads notes, the novice parts of the
described-loads note, and the reviewed or described load case each was scored with. The build123d
code is the code those notes measured, kept here so the measurement can be run again."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from cad.checks.container.wire import DirectionWire, LoadCaseWire, LoadWire, SupportWire

REPO: Final = Path(__file__).resolve().parents[2]
SANDBOX_PARTS: Final = REPO / "tests" / "sandbox" / "parts"
FORCE_N: Final = 20.0

ANY: Final[DirectionWire] = {"kind": "any"}
ACROSS_LONG: Final[DirectionWire] = {"kind": "across", "axis": "long"}
ACROSS_HOLE: Final[DirectionWire] = {"kind": "across", "axis": "hole_axis"}
ALONG_HOLE: Final[DirectionWire] = {"kind": "along", "axis": "hole_axis"}
INTO: Final[DirectionWire] = {"kind": "into"}
AWAY: Final[DirectionWire] = {"kind": "away"}
FLAT_END: Final[SupportWire] = {"kind": "flat_end"}
LARGEST_FLAT: Final[SupportWire] = {"kind": "largest_flat"}


def holes(count: int, diameter: float | None) -> SupportWire:
    return {"kind": "holes", "count": count, "diameter_mm": diameter}


def far_end(direction: DirectionWire) -> LoadWire:
    return {"kind": "far_end", "force_n": FORCE_N, "direction": direction}


def on_holes(count: int, diameter: float, direction: DirectionWire) -> LoadWire:
    return {
        "kind": "on_holes",
        "count": count,
        "diameter_mm": diameter,
        "force_n": FORCE_N,
        "direction": direction,
    }


def on_farthest(curve: str, diameter: float | None, direction: DirectionWire) -> LoadWire:
    assert curve in ("hole", "inner_curve")
    return {
        "kind": "on_farthest",
        "curve": "hole" if curve == "hole" else "inner_curve",
        "diameter_mm": diameter,
        "force_n": FORCE_N,
        "direction": direction,
    }


def on_largest_flat(middle: bool) -> LoadWire:
    return {"kind": "on_largest_flat", "middle": middle, "force_n": FORCE_N, "direction": INTO}


def on_opposite(middle: bool) -> LoadWire:
    return {"kind": "on_opposite", "middle": middle, "force_n": FORCE_N, "direction": INTO}


def case(support: SupportWire, load: LoadWire) -> LoadCaseWire:
    return {"support": support, "load": load}


@dataclass(frozen=True, slots=True)
class Part:
    name: str
    code: str
    words: str
    reviewed: LoadCaseWire | None
    """The case the corpus scored it with. None for a novice part."""
    described: tuple[tuple[str, LoadCaseWire], ...] = field(default=())
    """The described cases the described-loads note resolved on it, each with its label."""


MIN = "MIN = (Align.MIN, Align.MIN, Align.MIN)\n"
HEAD = "from build123d import *\n" + MIN

L_BASE = (
    HEAD
    + """\
wall = Pos(0, 0, -45) * Box(5, 30, 50, align=MIN)
arm = Box(100, 30, 5, align=MIN)
result = wall + arm
"""
)
L_HOLES = """\
for z in (-12, -35):
    result -= Pos(2.5, 15, z) * Rot(0, 90, 0) * Cylinder(2.25, 20)
"""
GUSSET = """\
web = make_face(Polyline((4.5, 0, 0.5), (4.5, 0, -40), (60, 0, 0.5), close=True))
result += Pos(0, 15, 0) * extrude(web, 2, both=True)
"""
L_FILLETED = (
    HEAD
    + """\
wall = Pos(0, 0, -45) * Box(5, 30, 50, align=MIN)
arm = Box(100, 30, 5, align=MIN)
result = wall + arm
inner = result.edges().filter_by(Axis.Y).filter_by(
    lambda e: abs(e.center().X - 5) < 1e-6 and abs(e.center().Z) < 1e-6
)
result = fillet(inner, 4)
outer = result.edges().filter_by(Axis.Y).filter_by(
    lambda e: abs(e.center().X) < 1e-6 and abs(e.center().Z - 5) < 1e-6
)
result = fillet(outer, 2)
tip = result.edges().filter_by(Axis.Z).filter_by(lambda e: abs(e.center().X - 100) < 1e-6)
result = fillet(tip, 3)
"""
    + L_HOLES
)
SHELF_WEB = (
    HEAD
    + """\
vert = Pos(0, 0, -80) * Box(4, 25, 80, align=MIN)
horiz = Pos(0, 0, -4) * Box(100, 25, 4, align=MIN)
web = make_face(Polyline((3.5, 0, -3.5), (3.5, 0, -76), (96, 0, -3.5), close=True))
result = vert + horiz + Pos(0, 12.5, 0) * extrude(web, 2, both=True)
for y in (5, 20):
    result -= Pos(2, y, -45) * Rot(0, 90, 0) * Cylinder(2.5, 10)
"""
)
HOOK = (
    HEAD
    + """\
plate = Pos(0, 0, -50) * Box(4, 20, 50, align=MIN)
arm = Pos(0, 0, -50) * Box(30, 20, 4, align=MIN)
ring = Pos(30, 10, -36) * Rot(90, 0, 0) * (Cylinder(14, 20) - Cylinder(10, 20))
half = ring & (Pos(30, 0, -60) * Box(20, 20, 40, align=MIN))
result = plate + arm + half
for z in (-15, -35):
    result -= Pos(2, 10, z) * Rot(0, 90, 0) * Cylinder(2, 10)
"""
)
PLATE_BOSS = (
    HEAD
    + """\
plate = Box(60, 40, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))
boss = Pos(0, 0, 5) * Cylinder(8, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
result = plate + boss
for x, y in [(sx * 24, sy * 14) for sx in (-1, 1) for sy in (-1, 1)]:
    result -= Pos(x, y, 0) * Cylinder(2, 20)
"""
)
T_ARM = (
    HEAD
    + """\
plate = Pos(0, -20, -20) * Box(4, 40, 40, align=MIN)
flange = Pos(0, -10, 17) * Box(100, 20, 3, align=MIN)
web = Pos(0, -1.5, 2) * Box(100, 3, 15, align=MIN)
result = plate + flange + web
for y in (-12, 12):
    result -= Pos(2, y, -8) * Rot(0, 90, 0) * Cylinder(2.25, 10)
"""
)
I_BEAM = """\
top = Pos(0, -8, 8) * Box(100, 16, 2, align=MIN)
bottom = Pos(0, -8, -10) * Box(100, 16, 2, align=MIN)
web = Pos(0, -0.8, -8) * Box(100, 1.6, 16, align=MIN)
"""
JOINTS = """\
joints = result.edges().filter_by(Axis.X).filter_by(
    lambda e: abs(abs(e.center().Y) - 0.8) < 1e-6 and abs(abs(e.center().Z) - 8) < 1e-6
)
result = fillet(joints, 1)
"""
I_BEAM_ARM = (
    HEAD
    + "plate = Pos(0, -20, -20) * Box(4, 40, 40, align=MIN)\n"
    + I_BEAM
    + "result = plate + top + bottom + web\n"
    + JOINTS
    + """\
for y in (-13, 13):
    result -= Pos(2, y, 0) * Rot(0, 90, 0) * Cylinder(2.25, 10)
"""
)
I_BEAM_FLAT = HEAD + I_BEAM + "result = top + bottom + web\n" + JOINTS
TRUSS_ARM = (
    HEAD
    + """\
plate = Pos(0, -20, -25) * Box(4, 40, 50, align=MIN)
side = make_face(Polyline((3.5, 0, 15), (100, 0, 15), (100, 0, 5), (3.5, 0, -15), close=True))
result = plate + extrude(side, 3, both=True)
for a, b, apex in ((15, 35, -7.5), (45, 65, -1.3), (72, 88, 3.9)):
    cut = make_face(Polyline((a, 0, 12), (b, 0, 12), ((a + b) / 2, 0, apex), close=True))
    result -= extrude(cut, 5, both=True)
for y in (-13, 13):
    result -= Pos(2, y, 0) * Rot(0, 90, 0) * Cylinder(2.25, 10)
"""
)
SQUARE_TAB = HEAD + "result = Box(50, 50, 4, align=MIN)\n"
EQUAL_ANGLE = HEAD + "result = Box(50, 30, 4, align=MIN) + Box(4, 30, 50, align=MIN)\n"
BAR = HEAD + "result = Box(100, 12, 8, align=MIN)\n"
SHELF = (
    HEAD
    + """\
plate = Pos(0, 0, 54) * Box(120, 200, 6, align=MIN)
flange = Box(6, 200, 60, align=MIN)
result = plate + flange
for y in (30, 100, 170):
    result -= Pos(0, y, 25) * Rot(0, 90, 0) * Cylinder(2.5, 20)
"""
)
RAIL_HOOK = (
    HEAD
    + """\
bar = Box(6, 10, 60, align=MIN)
top = Pos(-8, 5, 60) * Rot(90, 0, 0) * (Cylinder(14, 10) - Cylinder(8, 10))
top = top & Pos(-22, 0, 60) * Box(28, 10, 14, align=MIN)
bottom = Pos(16, 5, 0) * Rot(90, 0, 0) * (Cylinder(16, 10) - Cylinder(10, 10))
bottom = bottom & Pos(0, 0, -16) * Box(32, 10, 16, align=MIN)
result = bar + top + bottom
"""
)
CLAMP = (
    HEAD
    + """\
result = Box(60, 20, 50, align=MIN) - Pos(10, -1, 15) * Box(51, 22, 20, align=MIN)
"""
)
PLATE = HEAD + "result = Box(160, 40, 6, align=MIN)\n"


def sandbox(name: str) -> str:
    return (SANDBOX_PARTS / f"{name}.py").read_text()


CORPUS: Final[tuple[Part, ...]] = (
    Part("cantilever_bar", BAR, "a 100 mm bar fixed into the wall at one end, 20 N at the tip",
         case(FLAT_END, far_end(ACROSS_LONG))),
    Part("l_plain", L_BASE, "L bracket, its upright leg against the wall, 20 N at the arm's end",
         case(FLAT_END, far_end(ACROSS_LONG))),
    Part("l_holes", L_BASE + L_HOLES, "L bracket screwed through its 2 holes, 20 N at the end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("l_gusset", L_BASE + GUSSET + L_HOLES, "L bracket with a gusset, 2 holes, 20 N at the end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("l_filleted", L_FILLETED, "filleted L bracket screwed through 2 holes, 20 N at the end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("u_bracket", sandbox("u_bracket"), "U bracket glued down by its base, 20 N on the hole",
         case(LARGEST_FLAT, on_holes(1, 6, ANY))),
    Part("shelf_web", SHELF_WEB, "shelf bracket with a web, 2 holes, 20 N at the tip",
         case(holes(2, 5), far_end(ANY))),
    Part("hook", HOOK, "wall hook screwed through 2 holes, 20 N hung on the hook",
         case(holes(2, 4), far_end(ANY)),
         (("Holes(2, 4), OnFarthest(inner curve 20), across hole axis",
           case(holes(2, 4), on_farthest("inner_curve", 20.0, ACROSS_HOLE))),
          ("Holes(2, 4), OnFarthest(inner curve), Away",
           case(holes(2, 4), on_farthest("inner_curve", None, AWAY))))),
    Part("plate_boss", PLATE_BOSS, "plate bolted through 4 holes, 20 N sideways on the boss",
         case(holes(4, 4), far_end(ACROSS_HOLE))),
    Part("t_arm", T_ARM, "shelf arm, T section, 2 holes, 20 N at its end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("t_arm_flat_end", T_ARM, "the same T arm, fixed to the wall at one end",
         case(FLAT_END, far_end(ACROSS_LONG))),
    Part("i_beam_arm", I_BEAM_ARM, "I-beam arm, filleted joints, 2 holes, 20 N at its end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("truss_arm", TRUSS_ARM, "tapered truss arm with cut-outs, 2 holes, 20 N at its end",
         case(holes(2, 4.5), far_end(ANY))),
    Part("square_tab", SQUARE_TAB, "50 mm square tab fixed along one edge, 20 N at the other",
         case(FLAT_END, far_end(ANY))),
    Part("equal_angle", EQUAL_ANGLE, "equal-leg angle, one leg fixed, 20 N at the end of the other",
         case(FLAT_END, far_end(ANY))),
    Part("sb_gusset", sandbox("gusset"), "triangular gusset fixed at one end, 20 N at the other",
         case(FLAT_END, far_end(ACROSS_LONG))),
    Part("sb_arm", sandbox("arm"), "lever arm pinned through one end hole, 20 N at the other end",
         case(holes(1, 28), far_end(ACROSS_HOLE)),
         (("Each(hole 28), OnFarthest(hole 28), across hole axis",
           case({"kind": "each", "curve": "hole", "diameter_mm": 28.0},
                on_farthest("hole", 28.0, ACROSS_HOLE))),)),
    Part("sb_motor_plate", sandbox("motor_plate"), "motor plate bolted through 4 holes, 20 N pull",
         case(holes(4, 3.2), on_holes(1, 22, ALONG_HOLE))),
    Part("sb_l_bracket", sandbox("l_bracket"), "sandbox L bracket screwed through 2 holes, 20 N",
         case(holes(2, 5.1), far_end(ANY)),
         (("InOneFlatFace(2, 5.1), far end, any way",
           case({"kind": "in_one_flat_face", "count": 2, "diameter_mm": 5.1}, far_end(ANY))),)),
    Part("i_beam_flat", I_BEAM_FLAT, "I-beam shelf arm fixed into the wall at one end, 20 N",
         case(FLAT_END, far_end(ACROSS_LONG))),
)  # fmt: skip

NOVICE: Final[tuple[Part, ...]] = (
    Part("shelf", SHELF, "a shelf pressed in the middle, screwed through its back", None,
         (("Holes(3, 5), OnLargestFlat(middle), Into", case(holes(3, 5), on_largest_flat(True))),
          ("InOneFlatFace(3, 5), OnLargestFlat(middle), Into",
           case({"kind": "in_one_flat_face", "count": 3, "diameter_mm": 5.0},
                on_largest_flat(True))))),
    Part("rail_hook", RAIL_HOOK, "an S hook hung from a rail", None,
         (("Each(inner curve), OnFarthest(inner curve), Away",
           case({"kind": "each", "curve": "inner_curve", "diameter_mm": None},
                on_farthest("inner_curve", None, AWAY))),)),
    Part("clamp", CLAMP, "a clamp, one jaw held, the other pressed", None,
         (("Facing, OnOpposite, Into", case({"kind": "facing"}, on_opposite(False))),
          ("Facing, OnOpposite(middle), Into", case({"kind": "facing"}, on_opposite(True))))),
    Part("plate", PLATE, "a plate fixed at one end, pressed in the middle", None,
         (("FlatEnd, OnLargestFlat(middle), Into", case(FLAT_END, on_largest_flat(True))),
          ("EndOf(middle), OnLargestFlat(middle), Into",
           case({"kind": "end_of", "axis": "middle"}, on_largest_flat(True))))),
)  # fmt: skip

BY_NAME: Final = {part.name: part for part in (*CORPUS, *NOVICE)}

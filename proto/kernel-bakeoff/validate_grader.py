"""Run in .venv-b123d. Every reference must pass; each mutant must fail with its expected category."""
import subprocess
import sys
import tempfile
from pathlib import Path

from build123d import Axis, Box, Cylinder, Polyline, Pos, Rot, Shell, export_step, extrude, fillet, make_face

sys.path.insert(0, str(Path(__file__).parent))
from grade import ROOT, grade, oracles  # noqa: E402
from reference.build import PARTS, involute_gear_outline  # noqa: E402

tmp = Path(tempfile.mkdtemp())
failures = []


def expect(part_id, path, category):
    got = grade(part_id, path)
    ok = got["category"] == category
    print(f"{'ok  ' if ok else 'FAIL'} {part_id:14s} {Path(path).name:22s} want={category:14s} got={got['category']} {got['detail']}")
    if not ok:
        failures.append(part_id)


for part_id in oracles():
    expect(part_id, ROOT / "reference" / f"{part_id}.step", "pass")

plate = Box(100, 50, 6)
for x, y in [(42, 17), (-42, 17), (42, -17)]:
    plate -= Pos(x, y, 0) * Cylinder(2.55, 20)
export_step(plate, str(tmp / "plate_3holes.step"))
expect("plate", tmp / "plate_3holes.step", "features")

thick = Box(100, 50, 6.5)
for x, y in [(sx * 42, sy * 17) for sx in (-1, 1) for sy in (-1, 1)]:
    thick -= Pos(x, y, 0) * Cylinder(2.55, 20)
export_step(thick, str(tmp / "plate_thick.step"))
expect("plate", tmp / "plate_thick.step", "bbox")

shell = Shell(PARTS["plate"]().faces()[:-1])
export_step(shell, str(tmp / "plate_shell.step"))
expect("plate", tmp / "plate_shell.step", "invalid_solid")

two = Pos(200, 0, 0) * PARTS["plate"]() + PARTS["plate"]()
export_step(two, str(tmp / "plate_two.step"))
expect("plate", tmp / "plate_two.step", "invalid_solid")

gear23 = extrude(make_face(Polyline(*involute_gear_outline(z=23, m=52 / 25), close=True)), 10) - Cylinder(4, 40)
export_step(gear23, str(tmp / "gear_23t.step"))
expect("spur_gear", tmp / "gear_23t.step", "features")

round_bore = Cylinder(12.5, 10) - Cylinder(6.35, 20)
export_step(round_bore, str(tmp / "hex_round_bore.step"))
expect("hex_spacer", tmp / "hex_round_bore.step", "volume")

one_wall = Pos(0, 0, 1) * Box(40, 50, 2) + Pos(19, 0, 15) * Box(2, 50, 30) + Pos(-19, 0, 15) * Box(2, 50, 30)
one_wall = fillet(one_wall.edges().filter_by(Axis.Y).filter_by(
    lambda e: abs(e.center().Z - 2) < 1e-6 and abs(abs(e.center().X) - 18) < 1e-6), 2)
one_wall -= Pos(19, 0, 20) * Rot(0, 90, 0) * Cylinder(3, 4)
export_step(one_wall, str(tmp / "u_one_hole.step"))
expect("u_bracket", tmp / "u_one_hole.step", "features")

expect("plate", tmp / "does_not_exist.step", "no_output")

cq_script = f"""
import cadquery as cq
p = (cq.Workplane('XZ').rect(100, 50).extrude(6)
     .faces('>Y').workplane().rect(84, 34, forConstruction=True).vertices().hole(5.1))
cq.exporters.export(p, r'{tmp / "plate_cq_rotated.step"}')
"""
subprocess.run([str(ROOT / ".venv-cq/bin/python"), "-c", cq_script], check=True)
expect("plate", tmp / "plate_cq_rotated.step", "pass")

print(f"\n{len(failures)} failures" if failures else "\nall grader checks behave as expected")
sys.exit(1 if failures else 0)

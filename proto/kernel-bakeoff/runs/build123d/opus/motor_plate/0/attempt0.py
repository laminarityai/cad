import math
from build123d import *

plate_size = 60.0
thickness = 6.0
center_hole_d = 22.0
bolt_hole_d = 3.2
bolt_circle_d = 50.8
r = bolt_circle_d / 2

with BuildPart() as plate:
    Box(plate_size, plate_size, thickness)
    Hole(radius=center_hole_d / 2, depth=thickness)
    pts = [
        (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
        for a in (45, 135, 225, 315)
    ]
    with Locations(*[(x, y, thickness / 2) for x, y in pts]):
        Hole(radius=bolt_hole_d / 2, depth=thickness)

# Center hole: Hole cuts from the top face workplane by default; ensure through
part = plate.part
cyl = Cylinder(center_hole_d / 2, thickness * 2)
part = part - cyl
for x, y in pts:
    part = part - Pos(x, y, 0) * Cylinder(bolt_hole_d / 2, thickness * 2)

export_step(part, "out.step")

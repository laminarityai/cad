import math
from build123d import *

plate_size = 60.0
thickness = 6.0
center_hole_d = 22.0
bolt_hole_d = 3.2
bolt_circle_d = 50.8

with BuildPart() as part:
    Box(plate_size, plate_size, thickness)
    Hole(radius=center_hole_d / 2)
    r = bolt_circle_d / 2
    for ang in (45, 135, 225, 315):
        x = r * math.cos(math.radians(ang))
        y = r * math.sin(math.radians(ang))
        with Locations((x, y, thickness / 2)):
            Hole(radius=bolt_hole_d / 2)

result = part.part
export_step(result, "out.step")

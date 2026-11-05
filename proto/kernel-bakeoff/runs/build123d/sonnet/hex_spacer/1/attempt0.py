import math
from build123d import *

od = 25.0
length = 10.0
across_flats = 12.7
circ_radius = (across_flats / 2) / math.cos(math.radians(30))

with BuildPart() as part:
    Cylinder(radius=od / 2, height=length)
    with BuildSketch(Plane.XY.offset(-length / 2)):
        RegularPolygon(radius=circ_radius, side_count=6)
    extrude(amount=length, mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

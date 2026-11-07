from build123d import *

od = 25.0
length = 10.0
flats = 12.7
# RegularPolygon radius is circumradius by default; across flats = 2*R*cos(30deg)
import math
circ_r = (flats / 2) / math.cos(math.radians(30))

with BuildPart() as part:
    Cylinder(radius=od / 2, height=length)
    with BuildSketch(Plane.XY.offset(-length / 2)):
        RegularPolygon(radius=circ_r, side_count=6)
    extrude(amount=length, mode=Mode.SUBTRACT)

solid = part.part
export_step(solid, "out.step")

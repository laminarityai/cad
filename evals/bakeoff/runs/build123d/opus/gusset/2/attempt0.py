from build123d import *

T = 4.0
L = 50.0
HOLE_D = 20.0
R = 3.0

cx, cy = L / 3.0, L / 3.0

with BuildPart() as part:
    with BuildSketch(Plane.XY):
        Polygon((0, 0), (L, 0), (0, L), align=None)
    extrude(amount=T)
    fillet(part.edges().filter_by(Axis.Z), radius=R)
    with Locations((cx, cy, T)):
        Hole(radius=HOLE_D / 2.0, depth=T)

result = part.part
export_step(result, "out.step")

from build123d import *

leg = 50.0
thk = 4.0
hole_d = 20.0
r_corner = 3.0

cx, cy = leg / 3.0, leg / 3.0  # centroid of right triangle

with BuildPart() as part:
    with BuildSketch() as sk:
        Polygon((0, 0), (leg, 0), (0, leg), align=None)
        fillet(sk.vertices(), radius=r_corner)
    extrude(amount=thk)
    with Locations((cx, cy, thk)):
        Hole(radius=hole_d / 2, depth=thk)

result = part.part
export_step(result, "out.step")

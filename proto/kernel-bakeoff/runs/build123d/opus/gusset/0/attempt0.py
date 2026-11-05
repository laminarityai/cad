from build123d import *

leg = 50.0
thk = 4.0
hole_d = 20.0
r_corner = 3.0

cx = leg / 3.0
cy = leg / 3.0

with BuildPart() as part:
    with BuildSketch():
        Polygon((0, 0), (leg, 0), (0, leg), align=None)
    extrude(amount=thk)
    fillet(part.edges().filter_by(Axis.Z), radius=r_corner)
    with Locations((cx, cy, 0)):
        Cylinder(radius=hole_d / 2, height=thk * 3, mode=Mode.SUBTRACT)

export_step(part.part, "out.step")

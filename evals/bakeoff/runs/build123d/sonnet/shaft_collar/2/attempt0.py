from build123d import *

length = 10.0
od = 25.0
bore = 12.7
hole_d = 3.3

with BuildPart() as part:
    Cylinder(radius=od / 2, height=length)
    Cylinder(radius=bore / 2, height=length, mode=Mode.SUBTRACT)
    # Radial hole along +X, through one wall only (from outside to bore)
    wall_start = bore / 2
    hole_len = od / 2 - wall_start + 1.0
    with Locations(Plane.YZ.offset(wall_start - 0.5)):
        Cylinder(radius=hole_d / 2, height=hole_len + 0.5,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

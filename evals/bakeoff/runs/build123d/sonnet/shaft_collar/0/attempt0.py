from build123d import *

length = 10.0
od = 25.0
bore = 12.7
hole_d = 3.3

with BuildPart() as part:
    Cylinder(radius=od / 2, height=length)
    Cylinder(radius=bore / 2, height=length, mode=Mode.SUBTRACT)

    # Radial hole along +X, through one wall only (from outside into the bore)
    hole_len = od / 2 - bore / 2 + 1.0
    start_x = od / 2 + 1.0
    with Locations(Plane(origin=(start_x, 0, 0), z_dir=(-1, 0, 0))):
        Cylinder(radius=hole_d / 2, height=hole_len + 1.0 - 1.0 + 0.0,
                 align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

from build123d import *

OD = 25.0
BORE = 12.7
LENGTH = 10.0
HOLE_D = 3.3

with BuildPart() as collar:
    Cylinder(radius=OD / 2, height=LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    Cylinder(radius=BORE / 2, height=LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN),
             mode=Mode.SUBTRACT)
    # Radial hole along +X, from just inside bore to beyond outer wall (one wall only)
    hole_len = OD / 2 + 1.0
    with Locations(Location((0, 0, LENGTH / 2), (0, 90, 0))):
        Cylinder(radius=HOLE_D / 2, height=hole_len,
                 align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

part = collar.part
export_step(part, "out.step")

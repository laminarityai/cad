from build123d import *

OD = 25.0
BORE = 12.7
L = 10.0
HOLE = 3.3

with BuildPart() as part:
    Cylinder(OD / 2, L)
    Cylinder(BORE / 2, L, mode=Mode.SUBTRACT)
    # radial hole along +X, through one wall only (from outside to bore)
    r_mid = (OD / 2 + BORE / 2) / 2
    wall = OD / 2 - BORE / 2
    with Locations(Location((r_mid, 0, 0), (0, 90, 0))):
        Cylinder(HOLE / 2, wall + 2, mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

from build123d import *

OD = 25.0
ID = 12.7
L = 10.0
HOLE_D = 3.3

with BuildPart() as collar:
    Cylinder(radius=OD / 2, height=L)
    Cylinder(radius=ID / 2, height=L, mode=Mode.SUBTRACT)
    # Radial hole along +X at mid-length (z=0), through one wall only
    hole_len = OD / 2 - ID / 2 + 2.0  # extends past both wall surfaces
    hole_center_x = (ID / 2 + OD / 2) / 2
    with Locations(Pos(hole_center_x, 0, 0)):
        Cylinder(
            radius=HOLE_D / 2,
            height=hole_len,
            rotation=(0, 90, 0),
            mode=Mode.SUBTRACT,
        )

part = collar.part
export_step(part, "out.step")

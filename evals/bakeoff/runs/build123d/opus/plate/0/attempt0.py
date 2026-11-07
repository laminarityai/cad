from build123d import *

L, W, T = 100.0, 50.0, 6.0
hole_d = 5.1
inset = 8.0

with BuildPart() as plate:
    Box(L, W, T)
    with Locations(
        (-L / 2 + inset, -W / 2 + inset, 0),
        (L / 2 - inset, -W / 2 + inset, 0),
        (-L / 2 + inset, W / 2 - inset, 0),
        (L / 2 - inset, W / 2 - inset, 0),
    ):
        Cylinder(radius=hole_d / 2, height=T * 2, mode=Mode.SUBTRACT)

export_step(plate.part, "out.step")

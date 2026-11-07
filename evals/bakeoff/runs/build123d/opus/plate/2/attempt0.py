from build123d import *

L, W, T = 100.0, 50.0, 6.0
hole_d = 5.1
inset = 8.0

with BuildPart() as plate:
    Box(L, W, T)
    with Locations((0, 0, T / 2)):
        with GridLocations(L - 2 * inset, W - 2 * inset, 2, 2):
            Hole(radius=hole_d / 2, depth=T)

part = plate.part
export_step(part, "out.step")

from build123d import *

length, width, thickness = 100.0, 50.0, 6.0
hole_d = 5.1
inset = 8.0

with BuildPart() as part:
    Box(length, width, thickness)
    with Locations(
        (length / 2 - inset, width / 2 - inset),
        (-(length / 2 - inset), width / 2 - inset),
        (length / 2 - inset, -(width / 2 - inset)),
        (-(length / 2 - inset), -(width / 2 - inset)),
    ):
        Hole(radius=hole_d / 2)

result = part.part
export_step(result, "out.step")

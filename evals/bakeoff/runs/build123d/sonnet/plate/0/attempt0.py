from build123d import *

L, W, T = 100.0, 50.0, 6.0
d = 5.1
inset = 8.0

with BuildPart() as part:
    Box(L, W, T)
    with Locations(
        (L/2 - inset, W/2 - inset),
        (-(L/2 - inset), W/2 - inset),
        (L/2 - inset, -(W/2 - inset)),
        (-(L/2 - inset), -(W/2 - inset)),
    ):
        Hole(radius=d/2, depth=T)

export_step(part.part, "out.step")

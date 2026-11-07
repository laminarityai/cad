from build123d import *
import math

with BuildPart() as part:
    Box(60, 60, 6)
    Hole(11)
    r = 50.8 / 2
    with Locations(*[(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]):
        Hole(1.6)

export_step(part.part, "out.step")

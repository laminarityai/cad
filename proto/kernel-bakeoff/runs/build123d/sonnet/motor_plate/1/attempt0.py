from build123d import *
import math

with BuildPart() as part:
    Box(60, 60, 6)
    Hole(radius=11)
    r = 50.8 / 2
    with BuildSketch(Plane.XY.offset(3)):
        for a in (45, 135, 225, 315):
            with Locations((r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))):
                Circle(3.2 / 2)
    extrude(amount=-6, mode=Mode.SUBTRACT)

export_step(part.part, "out.step")

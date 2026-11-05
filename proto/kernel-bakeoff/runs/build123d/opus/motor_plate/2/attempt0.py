import math
from build123d import *

L = 60.0
T = 6.0
center_d = 22.0
bolt_d = 3.2
bc_d = 50.8
r = bc_d / 2

with BuildPart() as plate:
    Box(L, L, T)
    Cylinder(center_d / 2, T, mode=Mode.SUBTRACT)
    for ang in (45, 135, 225, 315):
        a = math.radians(ang)
        with Locations((r * math.cos(a), r * math.sin(a), 0)):
            Cylinder(bolt_d / 2, T, mode=Mode.SUBTRACT)

export_step(plate.part, "out.step")

from build123d import *

T = 3.0
W = 30.0
L = 40.0

# L profile in XZ plane, extruded along Y (width)
# Outside corner at origin; leg A along +X, leg B along +Z
with BuildPart() as bp:
    # Horizontal leg
    with Locations((L / 2, W / 2, T / 2)):
        Box(L, W, T)
    # Vertical leg
    with Locations((T / 2, W / 2, L / 2)):
        Box(T, W, L)

part = bp.part

# Holes in horizontal leg (through Z), distances measured from outside corner along X
for d in (12.0, 30.0):
    cyl = Pos(d, W / 2, T / 2) * Cylinder(radius=5.1 / 2, height=T + 2)
    part = part - cyl

# Holes in vertical leg (through X), distances along Z
for d in (12.0, 30.0):
    cyl = Pos(T / 2, W / 2, d) * Rot(Y=90) * Cylinder(radius=5.1 / 2, height=T + 2)
    part = part - cyl

export_step(part, "out.step")

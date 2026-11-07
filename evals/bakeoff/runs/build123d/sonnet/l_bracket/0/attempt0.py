from build123d import *

T, W, L = 3.0, 30.0, 40.0

with BuildPart() as bp:
    # Horizontal leg (along X)
    with Locations((L/2, W/2, T/2)):
        Box(L, W, T)
    # Vertical leg (along Z)
    with Locations((T/2, W/2, L/2)):
        Box(T, W, L)

part = bp.part

# Holes in horizontal leg (axis along Z)
for x in (12, 30):
    cyl = Pos(x, W/2, T/2) * Cylinder(5.1/2, T*3)
    part = part - cyl

# Holes in vertical leg (axis along X)
for z in (12, 30):
    cyl = Pos(T/2, W/2, z) * (Rot(0, 90, 0) * Cylinder(5.1/2, T*3))
    part = part - cyl

export_step(part, "out.step")

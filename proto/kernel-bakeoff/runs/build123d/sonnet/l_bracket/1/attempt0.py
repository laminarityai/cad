from build123d import *

T = 3.0
W = 30.0
L = 40.0

# L profile in XZ plane: horizontal leg along X, vertical leg along Z
# Outside corner at origin; extrude along Y (width)
with BuildPart() as bp:
    # Horizontal leg: x 0..L, z 0..T
    with Locations((L / 2, W / 2, T / 2)):
        Box(L, W, T)
    # Vertical leg: x 0..T, z 0..L
    with Locations((T / 2, W / 2, L / 2)):
        Box(T, W, L)

part = bp.part

# Holes in horizontal leg (through Z), at x = 12 and 30
for x in (12.0, 30.0):
    h = Cylinder(radius=5.1 / 2, height=T * 4).moved(Location((x, W / 2, T / 2)))
    part = part - h

# Holes in vertical leg (through X), at z = 12 and 30
for z in (12.0, 30.0):
    h = Cylinder(radius=5.1 / 2, height=T * 4).rotate(Axis.Y, 90).moved(Location((T / 2, W / 2, z)))
    part = part - h

export_step(part, "out.step")

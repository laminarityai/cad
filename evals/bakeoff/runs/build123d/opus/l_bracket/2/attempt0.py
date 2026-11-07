from build123d import *

T = 3.0
W = 30.0
L = 40.0
D = 5.1
positions = [12.0, 30.0]

# Horizontal leg: x 0..L, y 0..W, z 0..T
base = Box(L, W, T, align=(Align.MIN, Align.MIN, Align.MIN))
# Vertical leg: x 0..T, y 0..W, z 0..L
upright = Box(T, W, L, align=(Align.MIN, Align.MIN, Align.MIN))

part = base + upright

# Holes in horizontal leg (axis along Z)
for p in positions:
    hole = Cylinder(D / 2, T * 4)
    hole = Pos(p, W / 2, T / 2) * hole
    part = part - hole

# Holes in vertical leg (axis along X)
for p in positions:
    hole = Cylinder(D / 2, T * 4)
    hole = Pos(T / 2, W / 2, p) * Rot(0, 90, 0) * hole
    part = part - hole

if isinstance(part, Compound) and len(part.solids()) == 1:
    part = part.solids()[0]

export_step(part, "out.step")

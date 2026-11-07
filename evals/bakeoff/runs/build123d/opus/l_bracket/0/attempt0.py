from build123d import *

T = 3.0
W = 30.0
L = 40.0
D = 5.1

# Horizontal leg: x 0..L, y 0..W, z 0..T
horiz = Box(L, W, T, align=(Align.MIN, Align.MIN, Align.MIN))
# Vertical leg: x 0..T, y 0..W, z 0..L
vert = Box(T, W, L, align=(Align.MIN, Align.MIN, Align.MIN))

part = horiz + vert

for d in (12.0, 30.0):
    # Holes through horizontal leg (along Z)
    h = Cylinder(D / 2, T * 4)
    h = Pos(d, W / 2, T / 2) * h
    part = part - h
    # Holes through vertical leg (along X)
    v = Cylinder(D / 2, T * 4, rotation=(0, 90, 0))
    v = Pos(T / 2, W / 2, d) * v
    part = part - v

if isinstance(part, ShapeList):
    part = part[0]

export_step(part, "out.step")

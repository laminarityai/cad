from build123d import *

T = 3.0
W = 30.0
L = 40.0
D = 5.1

# Horizontal leg: along X, thickness in Z, width in Y
h_leg = Box(L, W, T, align=(Align.MIN, Align.MIN, Align.MIN))
# Vertical leg: along Z, thickness in X
v_leg = Box(T, W, L, align=(Align.MIN, Align.MIN, Align.MIN))

part = h_leg + v_leg

# Holes in horizontal leg (through Z), distances from outside corner (x=0)
for x in (12.0, 30.0):
    part -= Cylinder(D / 2, T * 4).moved(Location((x, W / 2, T / 2)))

# Holes in vertical leg (through X), distances from outside corner (z=0)
for z in (12.0, 30.0):
    cyl = Cylinder(D / 2, T * 4, rotation=(0, 90, 0))
    part -= cyl.moved(Location((T / 2, W / 2, z)))

export_step(part, "out.step")

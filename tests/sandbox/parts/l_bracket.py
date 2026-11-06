from build123d import Box, Cylinder, Pos, Rot

base = Pos(20, 15, 1.5) * Box(40, 30, 3)
wall = Pos(1.5, 15, 20) * Box(3, 30, 40)
result = base + wall
for d in (12, 30):
    result -= Pos(d, 15, 0) * Cylinder(2.55, 20)
    result -= Pos(0, 15, d) * Rot(0, 90, 0) * Cylinder(2.55, 20)

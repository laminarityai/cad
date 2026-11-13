from build123d import Box, Cylinder, Pos, Rot

wall = Pos(2, 0, 50) * Box(4, 40, 100)
arm = Pos(50, 0, 2) * Box(100, 40, 4)
rib = Pos(15, 0, 15) * Box(30, 6, 30)
result = wall + arm + rib
for z in (20, 80):
    result -= Pos(2, 0, z) * Rot(0, 90, 0) * Cylinder(2.75, 8)

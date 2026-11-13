from build123d import Box, Cylinder, Pos, Rot

wall = Pos(3, 0, 50) * Box(6, 40, 100)
arm = Pos(50, 0, 3) * Box(100, 40, 6)
result = wall + arm
for z in (20, 80):
    result -= Pos(3, 0, z) * Rot(0, 90, 0) * Cylinder(2.75, 10)

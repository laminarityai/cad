from build123d import Box, Cylinder, Pos, Rot

# x runs out from the wall, y along it, z up it. The wall plate is 4 mm thick and the arm 4 mm.
wall = Pos(2, 0, 50) * Box(4, 40, 100)
arm = Pos(50, 0, 2) * Box(100, 40, 4)
result = wall + arm
for z in (20, 80):
    result -= Pos(2, 0, z) * Rot(0, 90, 0) * Cylinder(2.75, 8)

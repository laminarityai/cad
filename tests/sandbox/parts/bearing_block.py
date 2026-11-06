from build123d import Box, Cylinder, Pos

result = Pos(0, 0, 10) * Box(40, 40, 20)
result -= Pos(0, 0, 20 - 4) * Cylinder(14, 8)
result -= Cylinder(6.35, 60)
for x, y in [(15, 15), (-15, -15)]:
    result -= Pos(x, y, 0) * Cylinder(2.55, 60)

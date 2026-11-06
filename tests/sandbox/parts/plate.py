from build123d import Box, Cylinder, Pos

result = Box(100, 50, 6)
for x, y in [(sx * 42, sy * 17) for sx in (-1, 1) for sy in (-1, 1)]:
    result -= Pos(x, y, 0) * Cylinder(2.55, 18)

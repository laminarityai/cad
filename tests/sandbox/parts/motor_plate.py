import math

from build123d import Box, Cylinder, Pos

result = Box(60, 60, 6) - Cylinder(11, 20)
r = 25.4
for a in (45, 135, 225, 315):
    x, y = r * math.cos(math.radians(a)), r * math.sin(math.radians(a))
    result -= Pos(x, y, 0) * Cylinder(1.6, 18)

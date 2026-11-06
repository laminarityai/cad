from build123d import Axis, Box, Cylinder, Pos, Rot, fillet

base = Pos(0, 0, 1) * Box(40, 50, 2)
walls = [Pos(sx * 19, 0, 15) * Box(2, 50, 30) for sx in (-1, 1)]
bracket = base + walls[0] + walls[1]
inside = (
    bracket.edges()
    .filter_by(Axis.Y)
    .filter_by(lambda e: abs(e.center().Z - 2) < 1e-6 and abs(abs(e.center().X) - 18) < 1e-6)
)
bracket = fillet(inside, 2)
result = bracket - Pos(0, 0, 20) * Rot(0, 90, 0) * Cylinder(3, 60)

from build123d import Axis, Cylinder, Polyline, Pos, extrude, fillet, make_face

triangle = make_face(Polyline((0, 0), (50, 0), (0, 50), close=True))
plate = extrude(triangle, 4)
plate = fillet(plate.edges().filter_by(Axis.Z), 3)
result = plate - Pos(50 / 3, 50 / 3, 0) * Cylinder(10, 20)

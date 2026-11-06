import math

from build123d import Cylinder, RegularPolygon, extrude

hex_face = RegularPolygon(12.7 / math.sqrt(3), 6)
result = Cylinder(12.5, 10) - extrude(hex_face, 20, both=True)

from build123d import Cylinder, Pos, Rot

tube = Cylinder(12.5, 10) - Cylinder(6.35, 20)
result = tube - Pos(9.5, 0, 0) * Rot(0, 90, 0) * Cylinder(1.65, 7)

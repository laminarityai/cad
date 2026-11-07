from build123d import *

OD = 25.0
BORE = 12.7
L = 10.0
HOLE_D = 3.3

outer = Cylinder(OD / 2, L, align=(Align.CENTER, Align.CENTER, Align.MIN))
bore = Cylinder(BORE / 2, L + 2, align=(Align.CENTER, Align.CENTER, Align.CENTER)).moved(
    Location((0, 0, L / 2))
)
collar = outer - bore

# Radial hole through one wall only (+X side), at mid-length
hole_len = OD / 2 + 2  # from axis outward past the OD
hole = Cylinder(HOLE_D / 2, hole_len, align=(Align.CENTER, Align.CENTER, Align.MIN))
hole = hole.moved(Location((0, 0, L / 2), (0, 90, 0)))
collar = collar - hole

if isinstance(collar, ShapeList):
    collar = collar[0]

export_step(collar, "out.step")

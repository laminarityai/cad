import cadquery as cq

OD = 25.0
BORE = 12.7
LENGTH = 10.0
HOLE_D = 3.3

# Tube along Z
collar = (
    cq.Workplane("XY")
    .circle(OD / 2)
    .circle(BORE / 2)
    .extrude(LENGTH)
)

# Radial hole along +X at mid-length, through one wall only
hole = (
    cq.Workplane("YZ")
    .workplane(offset=0)
    .center(0, LENGTH / 2)
    .circle(HOLE_D / 2)
    .extrude(OD / 2 + 1.0)
)

collar = collar.cut(hole)

cq.exporters.export(collar, "out.step")

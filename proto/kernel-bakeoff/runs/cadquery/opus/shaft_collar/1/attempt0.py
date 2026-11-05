import cadquery as cq

OD = 25.0
BORE = 12.7
LENGTH = 10.0
HOLE_D = 3.3

# Tube along Z
collar = (
    cq.Workplane("XY")
    .circle(OD / 2.0)
    .circle(BORE / 2.0)
    .extrude(LENGTH)
)

# Radial hole along +X at mid-length, through one wall only
hole = (
    cq.Workplane("YZ")
    .workplane(offset=BORE / 2.0 - 1.0)
    .center(0, LENGTH / 2.0)
    .circle(HOLE_D / 2.0)
    .extrude(OD / 2.0 - BORE / 2.0 + 2.0)
)

result = collar.cut(hole)

cq.exporters.export(result, "out.step")

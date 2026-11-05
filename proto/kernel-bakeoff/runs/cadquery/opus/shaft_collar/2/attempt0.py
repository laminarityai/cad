import cadquery as cq

OD = 25.0
ID = 12.7
L = 10.0
HOLE_D = 3.3

# Tube along Z
collar = (
    cq.Workplane("XY")
    .circle(OD / 2)
    .circle(ID / 2)
    .extrude(L)
)

# Radial hole along +X from outside into bore, one wall only, at mid-length
hole_len = OD / 2 - ID / 2 + 2.0  # through wall with overlap into bore
hole = (
    cq.Workplane("YZ", origin=(ID / 2 - 1.0, 0, L / 2))
    .circle(HOLE_D / 2)
    .extrude(hole_len + 1.0)
)

collar = collar.cut(hole)

cq.exporters.export(collar, "out.step")

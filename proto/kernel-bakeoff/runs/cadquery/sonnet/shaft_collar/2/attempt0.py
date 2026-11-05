import cadquery as cq

od = 25.0
bore = 12.7
length = 10.0
hole_d = 3.3

# Tube along Z axis
tube = (
    cq.Workplane("XY")
    .circle(od / 2)
    .circle(bore / 2)
    .extrude(length)
)

# Radial hole along +X, at mid-length, through one wall only
cutter = (
    cq.Workplane("YZ")
    .workplane(offset=0)
    .center(0, length / 2)
    .circle(hole_d / 2)
    .extrude(od / 2 + 1)
)

result = tube.cut(cutter)

cq.exporters.export(result, "out.step")

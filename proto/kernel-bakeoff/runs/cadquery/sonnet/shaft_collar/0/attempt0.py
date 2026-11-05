import cadquery as cq

od = 25.0
bore = 12.7
length = 10.0
hole_d = 3.3

# Tube along Z
tube = (
    cq.Workplane("XY")
    .circle(od / 2)
    .circle(bore / 2)
    .extrude(length)
)

# Radial hole along +X at mid-length, through one wall only
hole = (
    cq.Workplane("YZ")
    .workplane(offset=bore / 4)  # start inside the bore region
    .center(0, length / 2)
    .circle(hole_d / 2)
    .extrude(od / 2)  # goes out through the +X wall
)

result = tube.cut(hole)

cq.exporters.export(result, "out.step")

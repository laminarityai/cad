import cadquery as cq

# Tube along Z axis, 10 mm long
tube = (
    cq.Workplane("XY")
    .circle(12.5)
    .circle(6.35)
    .extrude(10)
)

# Radial hole along +X, at mid-length, through one wall only
hole = (
    cq.Workplane("YZ")
    .workplane(offset=0)
    .center(0, 5)
    .circle(3.3 / 2)
    .extrude(13)  # from axis out past outer surface (+X), single wall
)

result = tube.cut(hole)

cq.exporters.export(result, "out.step")

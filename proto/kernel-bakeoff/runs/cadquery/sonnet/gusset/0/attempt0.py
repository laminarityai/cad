import cadquery as cq

t = 4.0
leg = 50.0

plate = (
    cq.Workplane("XY")
    .polyline([(0, 0), (leg, 0), (0, leg)])
    .close()
    .extrude(t)
    .edges("|Z")
    .fillet(3)
)

c = leg / 3.0
hole = (
    cq.Workplane("XY")
    .center(c, c)
    .circle(10.0)
    .extrude(t)
)

result = plate.cut(hole)

cq.exporters.export(result, "out.step")

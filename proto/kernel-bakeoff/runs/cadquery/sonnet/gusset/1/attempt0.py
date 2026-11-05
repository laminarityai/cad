import cadquery as cq

leg = 50.0
t = 4.0
cx = leg / 3.0
cy = leg / 3.0

plate = (
    cq.Workplane("XY")
    .polyline([(0, 0), (leg, 0), (0, leg)])
    .close()
    .extrude(t)
    .edges("|Z")
    .fillet(3.0)
)

hole = (
    cq.Workplane("XY")
    .center(cx, cy)
    .circle(10.0)
    .extrude(t)
)

result = plate.cut(hole)

cq.exporters.export(result, "out.step")

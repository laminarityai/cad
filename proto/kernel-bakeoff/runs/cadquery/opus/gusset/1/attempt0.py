import cadquery as cq

leg = 50.0
thk = 4.0
hole_d = 20.0
r = 3.0

cx = leg / 3.0
cy = leg / 3.0

plate = (
    cq.Workplane("XY")
    .polyline([(0, 0), (leg, 0), (0, leg)])
    .close()
    .extrude(thk)
    .edges("|Z")
    .fillet(r)
)

hole = (
    cq.Workplane("XY")
    .center(cx, cy)
    .circle(hole_d / 2.0)
    .extrude(thk)
)

result = plate.cut(hole)

cq.exporters.export(result, "out.step")

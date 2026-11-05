import cadquery as cq

leg = 50.0
t = 4.0

# Right triangle with right angle at origin
pts = [(0, 0), (leg, 0), (0, leg)]
plate = cq.Workplane("XY").polyline(pts).close().extrude(t)

# Round the three vertical (through-thickness) edges
plate = plate.edges("|Z").fillet(3.0)

# Centroid of the triangle
cx, cy = leg / 3.0, leg / 3.0

# 20 mm through hole at centroid
hole = (
    cq.Workplane("XY")
    .center(cx, cy)
    .circle(10.0)
    .extrude(t)
)
plate = plate.cut(hole)

cq.exporters.export(plate, "out.step")

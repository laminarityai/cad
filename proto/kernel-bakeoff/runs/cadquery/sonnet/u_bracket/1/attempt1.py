import cadquery as cq

W, H, D, t = 40.0, 30.0, 50.0, 2.0

# U profile in XZ plane (local x = X, local y = Z), extruded along +Y
pts = [
    (-W / 2, 0),
    (W / 2, 0),
    (W / 2, H),
    (W / 2 - t, H),
    (W / 2 - t, t),
    (-W / 2 + t, t),
    (-W / 2 + t, H),
    (-W / 2, H),
]
body = cq.Workplane("XZ").polyline(pts).close().extrude(-D)

# Select only the two inside corner edges (parallel to Y)
inner_edges = [
    e
    for e in body.edges("|Y").vals()
    if abs(abs(e.Center().x) - (W / 2 - t)) < 1e-3 and abs(e.Center().z - t) < 1e-3
]
body = body.newObject(inner_edges).fillet(2.0)

# Cross hole through both walls along X, centered along depth, 20 mm above bottom
hole = (
    cq.Workplane("YZ")
    .workplane(offset=-W / 2 - 1)
    .center(D / 2, 20)
    .circle(3.0)
    .extrude(W + 2)
)
body = body.cut(hole)

cq.exporters.export(body, "out.step")

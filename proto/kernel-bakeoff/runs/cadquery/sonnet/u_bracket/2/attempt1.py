import cadquery as cq

W, H, D, T = 40.0, 30.0, 50.0, 2.0

# U profile in XZ plane, extruded along +Y (depth)
outer = cq.Workplane("XZ").rect(W, H, centered=(True, False)).extrude(-D)
inner = (
    cq.Workplane("XZ")
    .workplane()
    .center(0, T + (H - T) / 2)
    .rect(W - 2 * T, H - T)
    .extrude(-D)
)
body = outer.cut(inner)

# Fillet only the two inside corner edges (parallel to Y, at x=±(W/2-T), z=T)
edges = [
    e for e in body.edges("|Y").vals()
    if abs(abs(e.Center().x) - (W / 2 - T)) < 0.1 and abs(e.Center().z - T) < 0.1
]
body = body.newObject(edges).fillet(2.0)

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

import cadquery as cq

W, H, D, t = 40.0, 30.0, 50.0, 2.0

# U profile in XZ plane, extruded along Y (depth)
outer = cq.Workplane("XZ").rect(W, H, centered=(True, False)).extrude(-D)
inner = (
    cq.Workplane("XZ")
    .workplane(offset=0)
    .center(0, t + (H - t) / 2)
    .rect(W - 2 * t, H - t)
    .extrude(-D)
)
body = outer.cut(inner)

# Fillet the two inside corners (where walls meet base)
body = body.edges(
    cq.selectors.BoxSelector((-W / 2 + t - 0.1, -1, t - 0.1), (W / 2 - t + 0.1, D + 1, t + 0.1))
).fillet(2.0)

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

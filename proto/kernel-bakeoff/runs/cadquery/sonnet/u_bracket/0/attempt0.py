import cadquery as cq

W, H, D, T = 40.0, 30.0, 50.0, 2.0

# U profile in XY plane (X width, Y height), extruded along Z (depth)
outer = cq.Workplane("XY").rect(W, H, centered=(True, False)).extrude(D)
inner = (
    cq.Workplane("XY")
    .workplane(offset=0)
    .center(0, T + (H - T) / 2)
    .rect(W - 2 * T, H - T)
    .extrude(D)
)
body = outer.cut(inner)

# Fillet inside corners (edges parallel to Z at base/wall junction)
body = body.edges(
    cq.selectors.BoxSelector(
        (-W / 2 + T - 0.1, T - 0.1, -1), (W / 2 - T + 0.1, T + 0.1, D + 1)
    )
).edges("|Z").fillet(2.0)

# Through hole across both walls along X, centered on depth, 20 mm above bottom
hole = (
    cq.Workplane("YZ")
    .center(20, D / 2)
    .circle(3.0)
    .extrude(W / 2 + 1, both=True)
)
body = body.cut(hole)

cq.exporters.export(body, "out.step")

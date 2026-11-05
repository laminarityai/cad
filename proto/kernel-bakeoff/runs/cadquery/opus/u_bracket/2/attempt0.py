import cadquery as cq

W, H, D, t = 40.0, 30.0, 50.0, 2.0
fillet_r = 2.0
hole_d = 6.0
hole_z = 20.0

# Outer block: X = width, Y = depth, Z = height (bottom at z=0)
outer = cq.Workplane("XY").box(W, D, H, centered=(True, True, False))

# Inner cavity: open on top and both ends
inner = (
    cq.Workplane("XY")
    .workplane(offset=t)
    .box(W - 2 * t, D + 2, H, centered=(True, True, False))
)

bracket = outer.cut(inner)

# Fillet the two inside corners where walls meet base (edges along Y at z=t)
bracket = (
    bracket.edges("|Y")
    .edges(cq.selectors.BoxSelector((-W / 2 + t - 0.5, -D, t - 0.5),
                                    (W / 2 - t + 0.5, D, t + 0.5)))
    .fillet(fillet_r)
)

# Coaxial through holes in side walls, along X, centered in depth, 20 mm up
hole = (
    cq.Workplane("YZ")
    .workplane(offset=-W / 2 - 5)
    .center(0, hole_z)
    .circle(hole_d / 2)
    .extrude(W + 10)
)
bracket = bracket.cut(hole)

cq.exporters.export(bracket, "out.step")

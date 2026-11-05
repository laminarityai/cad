import cadquery as cq

W, D, H, T = 40.0, 50.0, 30.0, 2.0
R_FILLET = 2.0
HOLE_D = 6.0
HOLE_Z = 20.0

# Outer block
outer = cq.Workplane("XY").box(W, D, H, centered=(True, True, False))

# Remove interior (open top and both ends)
inner = (
    cq.Workplane("XY")
    .box(W - 2 * T, D + 20, H, centered=(True, True, False))
    .translate((0, 0, T))
)
body = outer.cut(inner)

# Fillet the two inside corners where walls meet base
body = (
    body.edges("|Y")
    .edges(cq.selectors.BoxSelector((-W / 2 + T - 0.5, -D, T - 0.5),
                                    (W / 2 - T + 0.5, D, T + 0.5)))
    .fillet(R_FILLET)
)

# Coaxial through holes in both side walls
hole = cq.Solid.makeCylinder(
    HOLE_D / 2, W + 20, cq.Vector(-W / 2 - 10, 0, HOLE_Z), cq.Vector(1, 0, 0)
)
body = body.cut(cq.Workplane("XY").add(hole))

result = body.val()
cq.exporters.export(cq.Workplane("XY").add(result), "out.step")

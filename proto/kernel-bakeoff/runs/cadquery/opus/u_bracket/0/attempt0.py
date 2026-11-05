import cadquery as cq

W, H, D, T = 40.0, 30.0, 50.0, 2.0
FILLET_R = 2.0
HOLE_D = 6.0
HOLE_Z = 20.0

# Outer block
body = cq.Workplane("XY").box(W, D, H, centered=(True, True, False))

# Remove interior (open top and both ends)
cut = (
    cq.Workplane("XY")
    .workplane(offset=T)
    .box(W - 2 * T, D + 2, H, centered=(True, True, False))
)
body = body.cut(cut)

# Fillet the two inside corners (edges parallel to Y at z=T, x=±(W/2-T))
def inner_corner(e):
    c = e.Center()
    return abs(c.z - T) < 1e-6 and abs(abs(c.x) - (W / 2 - T)) < 1e-6

body = body.edges("|Y").filter(inner_corner).fillet(FILLET_R)

# Coaxial through holes in both side walls
hole = (
    cq.Workplane("YZ")
    .workplane(offset=-W / 2 - 1)
    .center(0, HOLE_Z)
    .circle(HOLE_D / 2)
    .extrude(W + 2)
)
body = body.cut(hole)

cq.exporters.export(body, "out.step")

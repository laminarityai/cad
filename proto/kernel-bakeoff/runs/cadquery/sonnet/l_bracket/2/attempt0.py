import cadquery as cq

t = 3.0
w = 30.0
L = 40.0

# L profile in XZ plane, extruded along Y (width)
# Outside corner at origin; leg A along +X, leg B along +Z
pts = [(0, 0), (L, 0), (L, t), (t, t), (t, L), (0, L)]
body = cq.Workplane("XZ").polyline(pts).close().extrude(-w)  # XZ normal is -Y, so negative extrudes to +Y

# Holes in leg A (along X, through Z thickness)
for d in (12.0, 30.0):
    cyl = (cq.Workplane("XY").workplane(offset=-1)
           .center(d, w / 2).circle(5.1 / 2).extrude(t + 2))
    body = body.cut(cyl)

# Holes in leg B (along Z, through X thickness)
for d in (12.0, 30.0):
    cyl = (cq.Workplane("YZ").workplane(offset=-1)
           .center(w / 2, d).circle(5.1 / 2).extrude(t + 2))
    body = body.cut(cyl)

cq.exporters.export(body, "out.step")

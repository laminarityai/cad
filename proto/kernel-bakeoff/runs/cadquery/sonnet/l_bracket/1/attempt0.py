import cadquery as cq

t = 3.0
w = 30.0
L = 40.0

# L profile in XZ plane, extruded along Y (width)
# Outside corner at origin; leg A along +X, leg B along +Z
pts = [(0, 0), (L, 0), (L, t), (t, t), (t, L), (0, L)]
body = cq.Workplane("XZ").polyline(pts).close().extrude(-w)  # XZ normal is -Y; negative extrude goes +Y

# Holes in horizontal leg (along X), drilled through Z
for d in (12.0, 30.0):
    cutter = (cq.Workplane("XY").workplane(offset=-1)
              .center(d, w / 2).circle(5.1 / 2).extrude(t + 2))
    body = body.cut(cutter)

# Holes in vertical leg (along Z), drilled through X
for d in (12.0, 30.0):
    cutter = (cq.Workplane("YZ").workplane(offset=-1)
              .center(w / 2, d).circle(5.1 / 2).extrude(t + 2))
    body = body.cut(cutter)

cq.exporters.export(body, "out.step")

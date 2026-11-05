import cadquery as cq

t = 3.0
w = 30.0
L = 40.0

# L profile in XZ plane, extruded along Y (width)
# Outside corner at origin; leg A along +X, leg B along +Z
pts = [(0, 0), (L, 0), (L, t), (t, t), (t, L), (0, L)]
body = cq.Workplane("XZ").polyline(pts).close().extrude(-w)  # XZ normal is -Y, so negative extrudes to +Y

# Holes in horizontal leg (along X), drilled through Z, at x = 12 and 30, y = w/2
for x in (12.0, 30.0):
    cutter = (cq.Workplane("XY").center(x, w / 2).circle(5.1 / 2).extrude(t))
    body = body.cut(cutter)

# Holes in vertical leg (along Z), drilled through X, at z = 12 and 30, y = w/2
for z in (12.0, 30.0):
    cutter = (cq.Workplane("YZ").center(w / 2, z).circle(5.1 / 2).extrude(t))
    body = body.cut(cutter)

cq.exporters.export(body, "out.step")

import cadquery as cq

L = 40.0
W = 40.0
H = 20.0

pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7

mount_d = 5.1
inset = 5.0

# Base block, bottom at z=0, top at z=H
block = cq.Workplane("XY").box(L, W, H, centered=(True, True, False))

# Bearing pocket from the top face
pocket = (
    cq.Workplane("XY")
    .workplane(offset=H - pocket_depth)
    .circle(pocket_d / 2.0)
    .extrude(pocket_depth)
)

# Through bore on the same axis
bore = cq.Workplane("XY").circle(bore_d / 2.0).extrude(H)

# Two mounting holes at diagonally opposite corners
hx = L / 2.0 - inset
hy = W / 2.0 - inset
mounts = (
    cq.Workplane("XY")
    .pushPoints([(-hx, -hy), (hx, hy)])
    .circle(mount_d / 2.0)
    .extrude(H)
)

result = block.cut(pocket).cut(bore).cut(mounts)

cq.exporters.export(result, "out.step")

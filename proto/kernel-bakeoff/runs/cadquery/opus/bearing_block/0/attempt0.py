import cadquery as cq

L = 40.0
H = 20.0
pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7
mount_d = 5.1
inset = 5.0

block = cq.Workplane("XY").box(L, L, H, centered=(True, True, False))

# Through bore
bore = cq.Workplane("XY").circle(bore_d / 2).extrude(H)
block = block.cut(bore)

# Bearing pocket from top face
pocket = (
    cq.Workplane("XY")
    .workplane(offset=H - pocket_depth)
    .circle(pocket_d / 2)
    .extrude(pocket_depth)
)
block = block.cut(pocket)

# Mounting holes at diagonally opposite corners
c = L / 2 - inset
mounts = (
    cq.Workplane("XY")
    .pushPoints([(c, c), (-c, -c)])
    .circle(mount_d / 2)
    .extrude(H)
)
block = block.cut(mounts)

cq.exporters.export(block, "out.step")

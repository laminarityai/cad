import cadquery as cq

L = 40.0
H = 20.0
pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7
mount_d = 5.1
inset = 5.0

block = cq.Workplane("XY").box(L, L, H, centered=(True, True, False))

# Bearing pocket from top face
pocket = (
    cq.Workplane("XY")
    .workplane(offset=H - pocket_depth)
    .circle(pocket_d / 2)
    .extrude(pocket_depth)
)

# Through bore on same axis
bore = cq.Workplane("XY").circle(bore_d / 2).extrude(H)

# Mounting holes at two diagonally opposite corners
c = L / 2 - inset
mounts = (
    cq.Workplane("XY")
    .pushPoints([(c, c), (-c, -c)])
    .circle(mount_d / 2)
    .extrude(H)
)

result = block.cut(pocket).cut(bore).cut(mounts)

cq.exporters.export(result, "out.step")

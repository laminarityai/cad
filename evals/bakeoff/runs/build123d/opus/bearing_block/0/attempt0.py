from build123d import *

L = 40.0
H = 20.0
pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7
mount_d = 5.1
inset = 5.0

# Main block, bottom at z=0, top at z=H
block = Box(L, L, H, align=(Align.CENTER, Align.CENTER, Align.MIN))

# Bearing pocket from top face
pocket = Pos(0, 0, H - pocket_depth) * Cylinder(
    pocket_d / 2, pocket_depth, align=(Align.CENTER, Align.CENTER, Align.MIN)
)

# Through bore on same axis
bore = Cylinder(bore_d / 2, H, align=(Align.CENTER, Align.CENTER, Align.MIN))

# Mounting holes at diagonally opposite corners
c = L / 2 - inset
mounts = [
    Pos(x, y, 0) * Cylinder(mount_d / 2, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    for (x, y) in [(-c, -c), (c, c)]
]

part = block - pocket - bore
for m in mounts:
    part = part - m

export_step(part, "out.step")

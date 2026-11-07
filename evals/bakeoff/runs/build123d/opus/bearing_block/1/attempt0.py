from build123d import *

L = 40.0
H = 20.0
pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7
mount_d = 5.1
inset = 5.0

with BuildPart() as part:
    with Locations((0, 0, H / 2)):
        Box(L, L, H)
    top = part.faces().sort_by(Axis.Z)[-1]
    # Bearing pocket
    with Locations((0, 0, H - pocket_depth / 2)):
        Cylinder(pocket_d / 2, pocket_depth, mode=Mode.SUBTRACT)
    # Through bore
    with Locations((0, 0, H / 2)):
        Cylinder(bore_d / 2, H, mode=Mode.SUBTRACT)
    # Mounting holes at diagonally opposite corners
    c = L / 2 - inset
    with Locations((c, c, H / 2), (-c, -c, H / 2)):
        Cylinder(mount_d / 2, H, mode=Mode.SUBTRACT)

export_step(part.part, "out.step")

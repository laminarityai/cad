from build123d import *

L = 40.0
H = 20.0
pocket_d = 28.0
pocket_depth = 8.0
bore_d = 12.7
mount_d = 5.1
inset = 5.0

with BuildPart() as part:
    Box(L, L, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    # Bearing pocket from top face
    with Locations((0, 0, H - pocket_depth)):
        Cylinder(pocket_d / 2, pocket_depth, align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)
    # Through bore on same axis
    Cylinder(bore_d / 2, H, align=(Align.CENTER, Align.CENTER, Align.MIN),
             mode=Mode.SUBTRACT)
    # Mounting holes at diagonally opposite corners
    off = L / 2 - inset
    with Locations((-off, -off, 0), (off, off, 0)):
        Cylinder(mount_d / 2, H, align=(Align.CENTER, Align.CENTER, Align.MIN),
                 mode=Mode.SUBTRACT)

export_step(part.part, "out.step")

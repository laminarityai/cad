from build123d import *

T = 6.0
W = 40.0
C2C = 250.0
BORE_D = 28.0
POCKET_L = 30.0
POCKET_W = 20.0
POCKET_R = 3.0
pocket_x = [62.5, 125.0, 187.5]

with BuildPart() as arm:
    with BuildSketch() as sk:
        with Locations((C2C / 2, 0)):
            SlotCenterToCenter(C2C, W)
        with Locations((0, 0), (C2C, 0)):
            Circle(BORE_D / 2, mode=Mode.SUBTRACT)
        with Locations(*[(x, 0) for x in pocket_x]):
            RectangleRounded(POCKET_L, POCKET_W, POCKET_R, mode=Mode.SUBTRACT)
    extrude(amount=T)

export_step(arm.part, "out.step")

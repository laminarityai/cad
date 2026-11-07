from build123d import *

T = 6.0
W = 40.0
C2C = 250.0
BORE_D = 28.0
POCKET_L = 30.0
POCKET_W = 20.0
POCKET_R = 3.0

with BuildPart() as part:
    with BuildSketch():
        SlotCenterToCenter(C2C, W)
        with Locations((-C2C / 2, 0), (C2C / 2, 0)):
            Circle(BORE_D / 2, mode=Mode.SUBTRACT)
        with Locations(*[(-C2C / 2 + d, 0) for d in (62.5, 125.0, 187.5)]):
            RectangleRounded(POCKET_L, POCKET_W, POCKET_R, mode=Mode.SUBTRACT)
    extrude(amount=T)

export_step(part.part, "out.step")

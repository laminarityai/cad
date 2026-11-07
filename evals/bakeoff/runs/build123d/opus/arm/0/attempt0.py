from build123d import *

thickness = 6.0
width = 40.0
c2c = 250.0
bore_d = 28.0
pocket_len = 30.0
pocket_w = 20.0
pocket_r = 3.0

with BuildPart() as arm:
    with BuildSketch(Plane.XY):
        SlotCenterToCenter(c2c, width)
        with Locations((-c2c / 2, 0), (c2c / 2, 0)):
            Circle(bore_d / 2, mode=Mode.SUBTRACT)
        with Locations(*[(-c2c / 2 + d, 0) for d in (62.5, 125.0, 187.5)]):
            RectangleRounded(pocket_len, pocket_w, pocket_r, mode=Mode.SUBTRACT)
    extrude(amount=thickness)

export_step(arm.part, "out.step")

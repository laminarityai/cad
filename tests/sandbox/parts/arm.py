from build123d import Cylinder, Pos, RectangleRounded, SlotCenterToCenter, extrude

result = extrude(SlotCenterToCenter(250, 40), 6)
for x in (-125, 125):
    result -= Pos(x, 0, 0) * Cylinder(14, 30)
for d in (62.5, 125, 187.5):
    result -= Pos(-125 + d, 0, 3) * extrude(RectangleRounded(30, 20, 3), 20, both=True)

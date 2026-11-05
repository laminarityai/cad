from build123d import *

with BuildPart() as p:
    with BuildSketch():
        with Locations((125, 0)):
            SlotOverall(290, 40)
        with Locations((0, 0), (250, 0)):
            Circle(14, mode=Mode.SUBTRACT)
        with Locations((62.5, 0), (125, 0), (187.5, 0)):
            RectangleRounded(30, 20, 3, mode=Mode.SUBTRACT)
    extrude(amount=6)

result = p.part
export_step(result, "out.step")

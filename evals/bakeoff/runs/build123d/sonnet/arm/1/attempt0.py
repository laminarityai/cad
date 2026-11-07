from build123d import *

with BuildPart() as p:
    with BuildSketch():
        with Locations((0, 0)):
            SlotCenterToCenter(250, 40)
        # slot is centered at origin; shift handled below
    extrude(amount=6)

# Rebuild with first bore center at x=0
with BuildPart() as part:
    with BuildSketch():
        with Locations((125, 0)):
            SlotCenterToCenter(250, 40)
        with Locations((0, 0), (250, 0)):
            Circle(14, mode=Mode.SUBTRACT)
        with Locations((62.5, 0), (125, 0), (187.5, 0)):
            RectangleRounded(30, 20, 3, mode=Mode.SUBTRACT)
    extrude(amount=6)

result = part.part
export_step(result, "out.step")

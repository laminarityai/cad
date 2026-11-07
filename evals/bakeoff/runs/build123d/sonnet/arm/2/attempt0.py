from build123d import *

with BuildPart() as p:
    with BuildSketch():
        with Locations((0, 0)):
            SlotOverall(290, 40)
        # shift so first bore center at x=0 later
    extrude(amount=6)

plate = p.part
# Slot is centered at origin: bores at x = -125 and +125
with BuildPart() as q:
    add(plate)
    # bores
    with BuildSketch():
        with Locations((-125, 0), (125, 0)):
            Circle(14)
    extrude(amount=6, mode=Mode.SUBTRACT)
    # pockets: centers at 62.5,125,187.5 from first bore -> x = -62.5, 0, 62.5
    with BuildSketch():
        with Locations((-62.5, 0), (0, 0), (62.5, 0)):
            RectangleRounded(30, 20, 3)
    extrude(amount=6, mode=Mode.SUBTRACT)

result = q.part
export_step(result, "out.step")

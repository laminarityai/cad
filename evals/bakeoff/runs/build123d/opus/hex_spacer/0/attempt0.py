from build123d import *

OD = 25.0
LENGTH = 10.0
HEX_AF = 12.7  # 1/2 inch across flats

with BuildPart() as spacer:
    with BuildSketch(Plane.XY):
        Circle(OD / 2)
        RegularPolygon(radius=HEX_AF / 2, side_count=6, major_radius=False, mode=Mode.SUBTRACT)
    extrude(amount=LENGTH)

part = spacer.part
export_step(part, "out.step")

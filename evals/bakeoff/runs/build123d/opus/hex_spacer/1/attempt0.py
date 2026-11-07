from build123d import *

OD = 25.0
LENGTH = 10.0
HEX_AF = 12.7  # across flats

with BuildPart() as spacer:
    Cylinder(radius=OD / 2, height=LENGTH, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with BuildSketch(Plane.XY) as hex_sk:
        RegularPolygon(radius=HEX_AF / 2, side_count=6, major_radius=False)
    extrude(amount=LENGTH, mode=Mode.SUBTRACT)

part = spacer.part
export_step(part, "out.step")

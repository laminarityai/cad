from build123d import *

with BuildPart() as part:
    Box(40, 40, 20, align=(Align.CENTER, Align.CENTER, Align.MIN))
    top = 20
    # bearing pocket from top face
    with Locations((0, 0, top)):
        Cylinder(14, 8, align=(Align.CENTER, Align.CENTER, Align.MAX), mode=Mode.SUBTRACT)
    # central through hole
    Cylinder(6.35, 20, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    # mounting holes at diagonal corners
    for x, y in [(15, 15), (-15, -15)]:
        with Locations((x, y, 0)):
            Cylinder(2.55, 20, align=(Align.CENTER, Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

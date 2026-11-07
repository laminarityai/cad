from build123d import *

with BuildPart() as part:
    with BuildSketch() as sk:
        Polygon((0, 0), (50, 0), (0, 50), align=None)
        vertices = sk.vertices()
        fillet(vertices, radius=3)
        # centroid of right triangle with legs 50
        with Locations((50 / 3, 50 / 3)):
            Circle(10, mode=Mode.SUBTRACT)
    extrude(amount=4)

result = part.part
export_step(result, "out.step")

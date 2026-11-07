from build123d import *

t = 4
leg = 50

with BuildPart() as part:
    with BuildSketch() as sk:
        Polygon((0, 0), (leg, 0), (0, leg), align=None)
    extrude(amount=t)
    # Fillet the three vertical edges (through thickness)
    edges = part.edges().filter_by(Axis.Z)
    fillet(edges, radius=3)
    # Hole at centroid
    cx, cy = leg / 3, leg / 3
    with BuildSketch(Plane.XY.offset(t)) as hs:
        with Locations((cx, cy)):
            Circle(10)
    extrude(amount=-t, mode=Mode.SUBTRACT)

result = part.part
export_step(result, "out.step")

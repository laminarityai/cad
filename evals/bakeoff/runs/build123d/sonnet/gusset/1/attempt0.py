from build123d import *

with BuildPart() as part:
    with BuildSketch():
        with BuildLine():
            Polyline((0, 0), (50, 0), (0, 50), close=True)
        make_face()
        # Round the three corners
        vertices = sketch_vertices = None
    extrude(amount=4)
    # Fillet vertical edges (through-thickness)
    edges = part.edges().filter_by(Axis.Z)
    fillet(edges, radius=3)
    # Hole at centroid
    cx, cy = 50 / 3, 50 / 3
    with Locations((cx, cy, 4)):
        Hole(radius=10)

result = part.part
export_step(result, "out.step")

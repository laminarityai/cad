from build123d import *

W, H, D, T = 40.0, 30.0, 50.0, 2.0

# U profile in XZ plane (x width, z height), extruded along Y (depth)
with BuildPart() as bp:
    with BuildSketch(Plane.XZ) as sk:
        with Locations((0, H / 2)):
            Rectangle(W, H)
        with Locations((0, T + (H - T) / 2)):
            Rectangle(W - 2 * T, H - T, mode=Mode.SUBTRACT)
    extrude(amount=D / 2, both=True)

    # Fillet inside corners where walls meet base
    edges = bp.edges().filter_by(Axis.Y).filter_by(
        lambda e: abs(abs(e.center().X) - (W / 2 - T)) < 1e-6 and abs(e.center().Z - T) < 1e-6
    )
    fillet(edges, radius=2.0)

    # Through hole along X, centered on depth, 20 mm above bottom
    with BuildSketch(Plane.YZ.offset(-W / 2 - 1)) as hs:
        with Locations((0, 20)):
            Circle(3.0)
    extrude(amount=W + 2, mode=Mode.SUBTRACT)

result = bp.part
export_step(result, "out.step")

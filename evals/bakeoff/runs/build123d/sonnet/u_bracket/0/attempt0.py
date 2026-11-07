from build123d import *

W, H, D, t = 40, 30, 50, 2

# U profile in XZ plane, extruded along Y (depth)
with BuildPart() as bp:
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            pass
        outer = Rectangle(W, H, align=(Alignment.CENTER, Alignment.MIN))
        inner = Pos(0, t) * Rectangle(W - 2 * t, H, align=(Alignment.CENTER, Alignment.MIN))
        subtract(inner)
    extrude(amount=D / 2, both=True)

    # fillet inside corners where walls meet base
    edges = bp.edges().filter_by(Axis.Y).filter_by(
        lambda e: abs(abs(e.center().X) - (W / 2 - t)) < 1e-6 and abs(e.center().Z - t) < 1e-6
    )
    fillet(edges, radius=2)

    # cross hole through both walls along X at z=20, y=0
    with BuildSketch(Plane.YZ.offset(-W / 2)):
        with Locations((0, 20)):
            Circle(3)
    extrude(amount=W, mode=Mode.SUBTRACT)

result = bp.part
export_step(result, "out.step")

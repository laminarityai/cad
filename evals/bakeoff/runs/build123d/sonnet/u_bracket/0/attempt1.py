from build123d import *

W, H, D, t = 40, 30, 50, 2

with BuildPart() as bp:
    Box(W, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((0, 0, t)):
        Box(W - 2 * t, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN),
            mode=Mode.SUBTRACT)

    # fillet inside corners where walls meet base
    inner_edges = [
        e for e in bp.edges().filter_by(Axis.Y)
        if abs(abs(e.center().X) - (W / 2 - t)) < 1e-6 and abs(e.center().Z - t) < 1e-6
    ]
    fillet(inner_edges, radius=2)

    # cross hole through both walls along X at z=20, centered along length
    with Locations((0, 0, 20)):
        Cylinder(3, W * 2, rotation=(0, 90, 0), mode=Mode.SUBTRACT)

result = bp.part
export_step(result, "out.step")

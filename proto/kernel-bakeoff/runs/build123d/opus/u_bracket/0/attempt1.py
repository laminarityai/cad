from build123d import *

W, H, D, T = 40.0, 30.0, 50.0, 2.0
FILLET_R = 2.0
HOLE_D = 6.0
HOLE_Z = 20.0

with BuildPart() as bracket:
    with BuildSketch(Plane.XZ):
        Rectangle(W, H, align=(Align.CENTER, Align.MIN))
        with Locations((0, T)):
            Rectangle(W - 2 * T, H + 5, align=(Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
    extrude(amount=D / 2, both=True)

    # Fillet the two inside corners (edges along Y at z=T, |x|=W/2-T)
    inner_edges = [
        e for e in bracket.edges().filter_by(Axis.Y)
        if abs(e.center().Z - T) < 1e-4 and abs(abs(e.center().X) - (W / 2 - T)) < 1e-4
    ]
    fillet(inner_edges, radius=FILLET_R)

    # Coaxial through holes in both side walls
    with Locations(Location((0, 0, HOLE_Z), (0, 90, 0))):
        Cylinder(HOLE_D / 2, W + 10, mode=Mode.SUBTRACT)

result = bracket.part
export_step(result, "out.step")

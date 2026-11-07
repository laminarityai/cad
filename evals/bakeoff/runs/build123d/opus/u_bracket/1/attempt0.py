from build123d import *

W, D, H, T = 40.0, 50.0, 30.0, 2.0

outer = Box(W, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
inner = Pos(0, 0, T) * Box(W - 2 * T, D + 2, H, align=(Align.CENTER, Align.CENTER, Align.MIN))
part = outer - inner

inner_edges = (
    part.edges()
    .filter_by(Axis.Y)
    .filter_by(lambda e: abs(e.center().Z - T) < 1e-6 and abs(abs(e.center().X) - (W / 2 - T)) < 1e-6)
)
part = fillet(inner_edges, radius=2.0)

hole = Pos(0, 0, 20) * Rot(0, 90, 0) * Cylinder(3.0, W + 20)
part = part - hole

export_step(part, "out.step")

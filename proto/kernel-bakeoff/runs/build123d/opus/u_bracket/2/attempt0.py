from build123d import *

W, H, D, T = 40.0, 30.0, 50.0, 2.0
R_FILLET = 2.0
HOLE_D = 6.0
HOLE_Z = 20.0

# Outer block
outer = Box(W, D, H, align=(Align.CENTER, Align.CENTER, Align.MIN))

# Inner cavity: open top and both ends
inner = Pos(0, 0, T) * Box(
    W - 2 * T, D + 10, H, align=(Align.CENTER, Align.CENTER, Align.MIN)
)

part = outer - inner

# Fillet the two inside corners where walls meet the base
inner_edges = (
    part.edges()
    .filter_by(Axis.Y)
    .filter_by(lambda e: abs(e.center().Z - T) < 1e-6
               and abs(abs(e.center().X) - (W / 2 - T)) < 1e-6)
)
part = fillet(inner_edges, radius=R_FILLET)

# Coaxial through holes in both side walls (axis along X)
hole = Pos(0, 0, HOLE_Z) * Rot(0, 90, 0) * Cylinder(HOLE_D / 2, W + 20)
part = part - hole

export_step(part, "out.step")

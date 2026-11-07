from build123d import *

outer = Box(40, 50, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
inner = Pos(0, 0, 2) * Box(36, 50, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))
part = outer - inner

edges = [
    e for e in part.edges()
    if abs(abs(e.center().X) - 18) < 1e-3
    and abs(e.center().Z - 2) < 1e-3
    and abs(e.length - 50) < 1e-3
]
part = fillet(edges, radius=2)

hole = Pos(0, 0, 20) * (Rot(0, 90, 0) * Cylinder(3, 60))
part = part - hole

result = part.solid() if hasattr(part, "solid") else part
export_step(result, "out.step")

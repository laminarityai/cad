import cadquery as cq

T = 3.0
W = 30.0
L = 40.0
D = 5.1
hole_pos = [12.0, 30.0]

# Horizontal leg: x 0..L, y 0..W, z 0..T
base = cq.Workplane("XY").box(L, W, T, centered=False)
# Vertical leg: x 0..T, y 0..W, z 0..L
upright = cq.Workplane("XY").box(T, W, L, centered=False)

bracket = base.union(upright)

# Holes in horizontal leg (along Z)
for p in hole_pos:
    cyl = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .center(p, W / 2)
        .circle(D / 2)
        .extrude(T + 2)
    )
    bracket = bracket.cut(cyl)

# Holes in vertical leg (along X)
for p in hole_pos:
    cyl = (
        cq.Workplane("YZ")
        .workplane(offset=-1)
        .center(W / 2, p)
        .circle(D / 2)
        .extrude(T + 2)
    )
    bracket = bracket.cut(cyl)

result = bracket.clean()
cq.exporters.export(result, "out.step")

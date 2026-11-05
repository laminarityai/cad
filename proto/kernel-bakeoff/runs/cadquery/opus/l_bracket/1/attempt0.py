import cadquery as cq

T = 3.0
W = 30.0
L = 40.0
D = 5.1
hole_pos = [12.0, 30.0]

# Horizontal leg: x 0..L, y 0..W, z 0..T
horiz = cq.Workplane("XY").box(L, W, T, centered=False)
# Vertical leg: x 0..T, y 0..W, z 0..L
vert = cq.Workplane("XY").box(T, W, L, centered=False)

bracket = horiz.union(vert)

# Holes in horizontal leg (through Z)
for p in hole_pos:
    cyl = (
        cq.Workplane("XY")
        .workplane(offset=-1)
        .center(p, W / 2)
        .circle(D / 2)
        .extrude(T + 2)
    )
    bracket = bracket.cut(cyl)

# Holes in vertical leg (through X)
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

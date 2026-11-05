import cadquery as cq

T = 6.0
W = 40.0
R = 20.0
L = 290.0
C = 250.0
BORE = 28.0

# Plate with fully rounded ends, first bore center at origin
plate = (
    cq.Workplane("XY")
    .center(C / 2, 0)
    .slot2D(L, W, 0)
    .extrude(T)
)

# Bearing bores
plate = (
    plate.faces(">Z").workplane(origin=(0, 0, T))
    .pushPoints([(0, 0), (C, 0)])
    .hole(BORE)
)

# Lightening pockets (through)
for x in (62.5, 125.0, 187.5):
    pocket = (
        cq.Workplane("XY")
        .box(30.0, 20.0, T + 2, centered=(True, True, False))
        .translate((x, 0, -1))
        .edges("|Z")
        .fillet(3.0)
    )
    plate = plate.cut(pocket)

result = plate
cq.exporters.export(result, "out.step")

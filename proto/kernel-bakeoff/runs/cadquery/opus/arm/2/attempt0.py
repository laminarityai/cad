import cadquery as cq

T = 6.0
W = 40.0
L = 290.0
BORE_D = 28.0
BORE_SPACING = 250.0
POCKET_L = 30.0
POCKET_W = 20.0
POCKET_R = 3.0

# Base plate with fully rounded ends, centered at origin
plate = cq.Workplane("XY").slot2D(L, W, 0).extrude(T)

# Bearing bores at end radius centers
x0 = -BORE_SPACING / 2.0
plate = (
    plate.faces(">Z").workplane()
    .pushPoints([(x0, 0), (x0 + BORE_SPACING, 0)])
    .hole(BORE_D)
)

# Lightening pockets (through), centers at 62.5, 125, 187.5 from first bore
for d in (62.5, 125.0, 187.5):
    cx = x0 + d
    pocket = (
        cq.Workplane("XY")
        .center(cx, 0)
        .rect(POCKET_L, POCKET_W)
        .extrude(T + 2)
        .translate((0, 0, -1))
        .edges("|Z").fillet(POCKET_R)
    )
    plate = plate.cut(pocket)

result = plate.val()
cq.exporters.export(cq.Workplane().add(result), "out.step")

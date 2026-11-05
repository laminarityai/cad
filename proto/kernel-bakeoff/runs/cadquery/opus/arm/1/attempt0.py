import cadquery as cq

T = 6.0
W = 40.0
R = W / 2
C2C = 250.0
L = C2C + 2 * R  # 290
BORE_D = 28.0
POCKET_L = 30.0
POCKET_W = 20.0
POCKET_R = 3.0
POCKET_X = [62.5, 125.0, 187.5]

# Base plate with fully rounded ends (bore centers at x=0 and x=250)
plate = (
    cq.Workplane("XY")
    .center(C2C / 2, 0)
    .slot2D(L, W, 0)
    .extrude(T)
)

# Bearing bores
plate = (
    plate.faces(">Z").workplane(origin=(0, 0, T))
    .pushPoints([(0, 0), (C2C, 0)])
    .hole(BORE_D)
)

# Lightening pockets (through) with rounded corners
for x in POCKET_X:
    pocket = (
        cq.Workplane("XY")
        .center(x, 0)
        .rect(POCKET_L, POCKET_W)
        .extrude(T)
        .edges("|Z")
        .fillet(POCKET_R)
    )
    plate = plate.cut(pocket)

result = plate.val()
cq.exporters.export(cq.Workplane().add(result), "out.step")

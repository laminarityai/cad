import cadquery as cq

# Plate: bores at x=0 and x=250, end radius 20 -> overall length 290
plate = (
    cq.Workplane("XY")
    .center(125, 0)
    .slot2D(290, 40, 0)
    .extrude(6)
)

# Bearing bores
plate = (
    plate.faces(">Z").workplane(origin=(0, 0, 6))
    .pushPoints([(0, 0), (250, 0)])
    .hole(28)
)

# Lightening pockets
pockets = (
    cq.Workplane("XY")
    .pushPoints([(62.5, 0), (125, 0), (187.5, 0)])
    .rect(30, 20)
    .extrude(6)
    .edges("|Z").fillet(3)
)

result = plate.cut(pockets)

cq.exporters.export(result, "out.step")

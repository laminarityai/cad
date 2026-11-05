import cadquery as cq

# Plate: slot shape, bore centers 250 apart, end radius 20, width 40, thickness 6
plate = (
    cq.Workplane("XY")
    .center(125, 0)
    .slot2D(290, 40, 0)
    .extrude(6)
)

# Bearing bores at each end
plate = (
    plate.faces(">Z").workplane(origin=(0, 0, 6))
    .pushPoints([(0, 0), (250, 0)])
    .hole(28)
)

# Lightening pockets (30 long along X, 20 wide along Y), 3 mm corner radii
cutter = (
    cq.Workplane("XY")
    .pushPoints([(62.5, 0), (125, 0), (187.5, 0)])
    .rect(30, 20)
    .extrude(6)
    .edges("|Z")
    .fillet(3)
)
plate = plate.cut(cutter)

cq.exporters.export(plate, "out.step")

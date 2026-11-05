import cadquery as cq

block = cq.Workplane("XY").box(40, 40, 20, centered=(True, True, False))

# Bearing pocket from top face
block = block.faces(">Z").workplane().hole(28, 8)

# Central through hole
block = block.faces("<Z").workplane().hole(12.7)

# Mounting holes at diagonally opposite corners
block = (
    block.faces(">Z").workplane(centerOption="CenterOfBoundBox")
    .pushPoints([(15, 15), (-15, -15)])
    .hole(5.1)
)

cq.exporters.export(block, "out.step")

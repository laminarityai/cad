import math
import cadquery as cq

plate = cq.Workplane("XY").box(60, 60, 6)

# Center through hole
plate = plate.faces(">Z").workplane().hole(22)

# Bolt circle holes
r = 50.8 / 2
pts = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a))) for a in (45, 135, 225, 315)]
plate = plate.faces(">Z").workplane().pushPoints(pts).hole(3.2)

cq.exporters.export(plate, "out.step")

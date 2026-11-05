import math
import cadquery as cq

L = 60.0
T = 6.0
center_d = 22.0
hole_d = 3.2
bc_r = 50.8 / 2.0

pts = [
    (bc_r * math.cos(math.radians(a)), bc_r * math.sin(math.radians(a)))
    for a in (45, 135, 225, 315)
]

plate = (
    cq.Workplane("XY")
    .box(L, L, T)
    .faces(">Z").workplane()
    .hole(center_d)
    .faces(">Z").workplane()
    .pushPoints(pts)
    .hole(hole_d)
)

cq.exporters.export(plate, "out.step")

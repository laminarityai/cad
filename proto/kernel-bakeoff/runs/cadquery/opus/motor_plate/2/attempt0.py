import math
import cadquery as cq

# Plate parameters
L = 60.0
W = 60.0
T = 6.0
center_hole_d = 22.0
bolt_hole_d = 3.2
bolt_circle_d = 50.8

r = bolt_circle_d / 2.0
pts = [
    (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
    for a in (45, 135, 225, 315)
]

plate = (
    cq.Workplane("XY")
    .box(L, W, T)
    .faces(">Z").workplane()
    .hole(center_hole_d)
    .faces(">Z").workplane()
    .pushPoints(pts)
    .hole(bolt_hole_d)
)

cq.exporters.export(plate, "out.step")

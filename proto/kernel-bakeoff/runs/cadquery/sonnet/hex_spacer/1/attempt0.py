import math
import cadquery as cq

od = 25.0
length = 10.0
af = 12.7  # across flats
d_corners = af / math.cos(math.radians(30))

result = (
    cq.Workplane("XY")
    .circle(od / 2)
    .extrude(length)
    .faces(">Z").workplane()
    .polygon(6, d_corners)
    .cutThruAll()
)

cq.exporters.export(result, "out.step")

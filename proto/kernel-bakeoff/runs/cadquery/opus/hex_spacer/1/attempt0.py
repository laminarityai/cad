import math
import cadquery as cq

od = 25.0
length = 10.0
hex_af = 12.7
hex_ac = hex_af / math.cos(math.radians(30))  # across corners (circumscribed diameter)

spacer = (
    cq.Workplane("XY")
    .circle(od / 2.0)
    .extrude(length)
    .faces(">Z")
    .workplane()
    .polygon(6, hex_ac)
    .cutThruAll()
)

cq.exporters.export(spacer, "out.step")

import cadquery as cq
import math

od = 25.0
length = 10.0
af = 12.7  # across flats
hex_diam = af / math.cos(math.radians(30))  # circumscribed diameter

spacer = (
    cq.Workplane("XY")
    .circle(od / 2)
    .extrude(length)
    .faces(">Z")
    .workplane()
    .polygon(6, hex_diam)
    .cutThruAll()
)

cq.exporters.export(spacer, "out.step")

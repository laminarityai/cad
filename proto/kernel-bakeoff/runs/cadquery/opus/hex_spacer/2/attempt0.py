import math
import cadquery as cq

od = 25.0
length = 10.0
hex_af = 12.7  # across flats
hex_ac = hex_af / math.cos(math.radians(30))  # across corners (circumscribed diameter)

body = cq.Workplane("XY").circle(od / 2).extrude(length)
bore = cq.Workplane("XY").polygon(6, hex_ac).extrude(length)

result = body.cut(bore)

cq.exporters.export(result, "out.step")

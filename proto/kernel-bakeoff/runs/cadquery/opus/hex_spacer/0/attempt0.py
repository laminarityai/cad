import math
import cadquery as cq

od = 25.0
length = 10.0
hex_af = 12.7
hex_circ_d = hex_af / math.cos(math.radians(30))

spacer = (
    cq.Workplane("XY")
    .circle(od / 2.0)
    .extrude(length)
)

hex_cut = (
    cq.Workplane("XY")
    .workplane(offset=-1.0)
    .polygon(6, hex_circ_d)
    .extrude(length + 2.0)
)

result = spacer.cut(hex_cut)

cq.exporters.export(result, "out.step")

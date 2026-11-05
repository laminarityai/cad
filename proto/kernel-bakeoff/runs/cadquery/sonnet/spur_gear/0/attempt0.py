import math
import cadquery as cq

z = 24
m = 2.0
pa = math.radians(20)
thickness = 10.0
bore = 8.0

rp = m * z / 2
rb = rp * math.cos(pa)
ra = rp + m
rr = rp - 1.25 * m

def inv(a):
    return math.tan(a) - a

invp = inv(pa)

def half_angle(r):
    a = math.acos(min(1.0, rb / r))
    return math.pi / (2 * z) + invp - inv(a)

def pt(r, th):
    return (r * math.cos(th), r * math.sin(th))

n = 10
radii = [rb + (ra - rb) * i / n for i in range(n + 1)]
pts = []
pitch = 2 * math.pi / z
for i in range(z):
    c = i * pitch
    hb = half_angle(rb)
    # root point, right flank rising
    pts.append(pt(rr, c - hb))
    for r in radii:
        pts.append(pt(r, c - half_angle(r)))
    # tip midpoint
    pts.append(pt(ra, c))
    for r in reversed(radii):
        pts.append(pt(r, c + half_angle(r)))
    pts.append(pt(rr, c + hb))
    # root circle midpoint in gap
    pts.append(pt(rr, c + pitch / 2))

gear = (
    cq.Workplane("XY")
    .polyline(pts)
    .close()
    .extrude(thickness)
)
gear = gear.cut(
    cq.Workplane("XY").circle(bore / 2).extrude(thickness)
)

cq.exporters.export(gear, "out.step")

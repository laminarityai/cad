import math
import cadquery as cq

m = 2.0
z = 24
alpha = math.radians(20)
thickness = 10.0
bore_d = 8.0

rp = m * z / 2
rb = rp * math.cos(alpha)
ra = rp + m
rr = rp - 1.25 * m

def inv(a):
    return math.tan(a) - a

# half tooth angle at the base circle
hb = (math.pi / 2 / z) + inv(alpha)

def flank_angle(r):
    a = math.acos(min(1.0, rb / r))
    return hb - inv(a)

n = 12
radii = [rb + (ra - rb) * i / (n - 1) for i in range(n)]
pitch_ang = 2 * math.pi / z

pts = []
for i in range(z):
    c = i * pitch_ang
    # right flank rising (root, then base to tip)
    pts.append((rr * math.cos(c - hb), rr * math.sin(c - hb)))
    for r in radii:
        t = c - flank_angle(r)
        pts.append((r * math.cos(t), r * math.sin(t)))
    # left flank descending
    for r in reversed(radii):
        t = c + flank_angle(r)
        pts.append((r * math.cos(t), r * math.sin(t)))
    pts.append((rr * math.cos(c + hb), rr * math.sin(c + hb)))
    # root arc to next tooth
    start = c + hb
    end = c + pitch_ang - hb
    for k in range(1, 4):
        t = start + (end - start) * k / 4
        pts.append((rr * math.cos(t), rr * math.sin(t)))

gear = (
    cq.Workplane("XY")
    .polyline(pts)
    .close()
    .extrude(thickness)
)

gear = gear.cut(
    cq.Workplane("XY").circle(bore_d / 2).extrude(thickness)
)

cq.exporters.export(gear, "out.step")

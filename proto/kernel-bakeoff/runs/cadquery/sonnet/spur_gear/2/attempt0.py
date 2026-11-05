import math
import cadquery as cq

m = 2.0
z = 24
alpha = math.radians(20)
thickness = 10.0
bore = 8.0

rp = m * z / 2
rb = rp * math.cos(alpha)
ra = rp + m
rr = rp - 1.25 * m

def inv(a):
    return math.tan(a) - a

theta0 = math.pi / (2 * z) + inv(alpha)  # half-tooth angle at base circle

def pol(r, a):
    return (r * math.cos(a), r * math.sin(a))

n = 10
r_start = max(rb, rr)
pts = []
pitch_ang = 2 * math.pi / z
for i in range(z):
    c = i * pitch_ang
    # right flank
    right = []
    for k in range(n + 1):
        r = rb + (ra - rb) * k / n
        a = math.acos(rb / r)
        right.append((r, -(theta0 - inv(a))))
    pts.append(pol(rr, c - theta0))
    for r, a in right:
        pts.append(pol(r, c + a))
    # tip mid point
    pts.append(pol(ra, c))
    for r, a in reversed(right):
        pts.append(pol(r, c - a))
    pts.append(pol(rr, c + theta0))
    # root mid point
    pts.append(pol(rr, c + pitch_ang / 2))

# remove consecutive duplicates
clean = []
for p in pts:
    if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
        clean.append(p)
if math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) < 1e-6:
    clean.pop()

gear = cq.Workplane("XY").polyline(clean).close().extrude(thickness)
gear = gear.cut(cq.Workplane("XY").circle(bore / 2).extrude(thickness))

cq.exporters.export(gear, "out.step")

from build123d import *
import math

z = 24
m = 2.0
alpha = math.radians(20)
thickness = 10.0
bore = 8.0

rp = m * z / 2
rb = rp * math.cos(alpha)
ra = rp + m
rr = rp - 1.25 * m

def inv(a):
    return math.tan(a) - a

def half_angle(r):
    # angular half-thickness of tooth at radius r
    a = math.acos(min(1.0, rb / r))
    return math.pi / (2 * z) + inv(alpha) - inv(a)

n = 12
radii = [max(rb, rr) + (ra - rb) * i / (n - 1) for i in range(n)]
pitch_ang = 2 * math.pi / z

pts = []
for t in range(z):
    c = t * pitch_ang
    hb = half_angle(rb)
    # root start point (radial line down to root circle)
    pts.append((rr * math.cos(c - hb), rr * math.sin(c - hb)))
    # right flank ascending
    for r in radii:
        th = c - half_angle(r)
        pts.append((r * math.cos(th), r * math.sin(th)))
    # left flank descending
    for r in reversed(radii):
        th = c + half_angle(r)
        pts.append((r * math.cos(th), r * math.sin(th)))
    # root end point and root arc to next tooth
    pts.append((rr * math.cos(c + hb), rr * math.sin(c + hb)))
    nxt = c + pitch_ang - hb
    start = c + hb
    for k in range(1, 4):
        th = start + (nxt - start) * k / 4
        pts.append((rr * math.cos(th), rr * math.sin(th)))

with BuildPart() as gear:
    with BuildSketch():
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
    extrude(amount=thickness)
    Cylinder(bore / 2, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN),
             mode=Mode.SUBTRACT)

export_step(gear.part, "out.step")

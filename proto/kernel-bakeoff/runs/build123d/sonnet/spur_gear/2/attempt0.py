from build123d import *
import math

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

def psi(r):
    ar = math.acos(min(1.0, rb / r))
    return math.pi / (2 * z) + inv(alpha) - inv(ar)

def pt(r, a):
    return (r * math.cos(a), r * math.sin(a))

pitch = 2 * math.pi / z
n_flank = 12
pts = []
for i in range(z):
    tc = i * pitch
    # right flank, rising
    rs = [rb + (ra - rb) * k / n_flank for k in range(n_flank + 1)]
    pts.append(pt(rr, tc - psi(rb)))
    for r in rs:
        pts.append(pt(r, tc - psi(r)))
    # tip midpoint
    pts.append(pt(ra, tc))
    # left flank, descending
    for r in reversed(rs):
        pts.append(pt(r, tc + psi(r)))
    pts.append(pt(rr, tc + psi(rb)))
    # root arc to next tooth
    a0 = tc + psi(rb)
    a1 = tc + pitch - psi(rb)
    for k in range(1, 4):
        pts.append(pt(rr, a0 + (a1 - a0) * k / 4))

# remove consecutive duplicates
clean = []
for p in pts:
    if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
        clean.append(p)
if math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) < 1e-6:
    clean.pop()

wire = Polyline(*clean, close=True)
face = make_face(wire)
gear = extrude(face, thickness)
bore = Cylinder(bore_d / 2, thickness, align=(Align.CENTER, Align.CENTER, Align.MIN))
result = gear - bore

export_step(result, "out.step")

import math
from build123d import *

# Gear parameters
m = 2.0
z = 24
pa = math.radians(20.0)
thickness = 10.0
bore_d = 8.0

rp = m * z / 2.0            # pitch radius
rb = rp * math.cos(pa)      # base radius
ra = rp + 1.0 * m           # addendum radius
rf = rp - 1.25 * m          # root radius


def inv(a):
    return math.tan(a) - a


def psi(r):
    """Half tooth thickness angle at radius r."""
    if r <= rb:
        r = rb
    ar = math.acos(rb / r)
    return math.pi / (2 * z) + inv(pa) - inv(ar)


def pt(r, ang):
    return (r * math.cos(ang), r * math.sin(ang))


n_flank = 20
n_tip = 6
n_root = 6

# radii along the involute flank (base -> tip)
r_start = max(rb, rf)
flank_r = [r_start + (ra - r_start) * i / n_flank for i in range(n_flank + 1)]

pts = []
pitch_ang = 2 * math.pi / z
for i in range(z):
    th = i * pitch_ang
    # right flank (going up)
    if rf < rb:
        pts.append(pt(rf, th - psi(rb)))
    for r in flank_r:
        pts.append(pt(r, th - psi(r)))
    # tip arc (interior points)
    a0 = th - psi(ra)
    a1 = th + psi(ra)
    for k in range(1, n_tip):
        pts.append(pt(ra, a0 + (a1 - a0) * k / n_tip))
    # left flank (going down)
    for r in reversed(flank_r):
        pts.append(pt(r, th + psi(r)))
    if rf < rb:
        pts.append(pt(rf, th + psi(rb)))
    # root arc (interior points) to next tooth
    b0 = th + psi(rb)
    b1 = th + pitch_ang - psi(rb)
    for k in range(1, n_root):
        pts.append(pt(rf, b0 + (b1 - b0) * k / n_root))

profile = make_face(Polyline(*pts, close=True))
gear = extrude(profile, amount=thickness)

bore = Cylinder(bore_d / 2.0, thickness + 2, align=(Align.CENTER, Align.CENTER, Align.MIN))
gear = gear - Pos(0, 0, -1) * bore

export_step(gear, "out.step")

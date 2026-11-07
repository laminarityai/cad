import math
from build123d import *

z = 24
m = 2.0
pa = math.radians(20)
thk = 10.0
bore_d = 8.0

r = m * z / 2.0
rb = r * math.cos(pa)
ra = r + m
rf = r - 1.25 * m

def inv(a):
    return math.tan(a) - a

def psi(rad):
    rr = max(rad, rb)
    a = math.acos(rb / rr)
    return math.pi / (2 * z) + inv(pa) - inv(a)

def pol(rad, ang):
    return (rad * math.cos(ang), rad * math.sin(ang))

n_flank = 20
flank_r = [rb + (ra - rb) * (k / (n_flank - 1)) for k in range(n_flank)]
if rf < rb:
    flank_r = [rf] + flank_r
else:
    flank_r = [rr for rr in flank_r if rr >= rf]
    flank_r = [rf] + flank_r

pts = []
pitch = 2 * math.pi / z
psi_root = psi(flank_r[0])
for i in range(z):
    th = i * pitch
    # left flank (going outward)
    for rr in flank_r:
        pts.append(pol(rr, th - psi(rr)))
    # tip arc
    psi_tip = psi(ra)
    n_tip = 4
    for k in range(1, n_tip):
        a = th - psi_tip + 2 * psi_tip * k / n_tip
        pts.append(pol(ra, a))
    # right flank (going inward)
    for rr in reversed(flank_r):
        pts.append(pol(rr, th + psi(rr)))
    # root arc to next tooth
    a0 = th + psi_root
    a1 = th + pitch - psi_root
    n_root = 5
    for k in range(1, n_root):
        a = a0 + (a1 - a0) * k / n_root
        pts.append(pol(rf, a))

with BuildPart() as gear:
    with BuildSketch():
        with BuildLine():
            Polyline(*pts, close=True)
        make_face()
        Circle(bore_d / 2, mode=Mode.SUBTRACT)
    extrude(amount=thk)

export_step(gear.part, "out.step")

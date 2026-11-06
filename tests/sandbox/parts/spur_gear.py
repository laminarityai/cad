import math

from build123d import Cylinder, Polyline, extrude, make_face


def inv(a):
    return math.tan(a) - a


def involute_gear_outline(z=24, m=2.0, pa_deg=20.0, n=40):
    pa = math.radians(pa_deg)
    rp, ra, rf = z * m / 2, z * m / 2 + m, z * m / 2 - 1.25 * m
    rb = rp * math.cos(pa)
    half_pitch_thick = math.pi / (2 * z)
    flank = []
    start = max(rb, rf)
    if rf < rb:
        flank.append((rf, half_pitch_thick + inv(pa)))
    for i in range(n + 1):
        r = start + (ra - start) * i / n
        a_r = math.acos(min(1.0, rb / r))
        flank.append((r, half_pitch_thick + inv(pa) - inv(a_r)))
    pts = []
    for k in range(z):
        c = 2 * math.pi * k / z
        for r, a in flank:
            pts.append((r * math.cos(c - a), r * math.sin(c - a)))
        for r, a in reversed(flank):
            pts.append((r * math.cos(c + a), r * math.sin(c + a)))
    return pts


face = make_face(Polyline(*involute_gear_outline(), close=True))
result = extrude(face, 10) - Cylinder(4, 40)

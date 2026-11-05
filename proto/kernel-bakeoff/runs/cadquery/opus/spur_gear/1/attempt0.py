import math
import cadquery as cq

# Gear parameters
z = 24
m = 2.0
alpha = math.radians(20.0)
thickness = 10.0
bore_d = 8.0

rp = m * z / 2.0              # pitch radius
rb = rp * math.cos(alpha)     # base radius
ra = rp + 1.0 * m             # addendum radius
rf = rp - 1.25 * m            # root radius


def inv(a):
    return math.tan(a) - a


def half_angle(r):
    """Angular half-thickness of tooth at radius r (r >= rb)."""
    ar = math.acos(min(1.0, rb / r))
    return math.pi / (2 * z) + inv(alpha) - inv(ar)


def pol(r, t):
    return (r * math.cos(t), r * math.sin(t))


n_flank = 20
n_tip = 6
n_root = 8
pitch_ang = 2 * math.pi / z

pts = []
r_start = max(rb, rf)
for i in range(z):
    t0 = i * pitch_ang
    # radial segment from root to base circle (root is below base here)
    psi_b = half_angle(r_start)
    pts.append(pol(rf, t0 - psi_b))
    # right flank (rising)
    flank_r = [r_start + (ra - r_start) * k / n_flank for k in range(n_flank + 1)]
    for r in flank_r:
        pts.append(pol(r, t0 - half_angle(r)))
    # tip arc
    psi_a = half_angle(ra)
    for k in range(1, n_tip):
        t = t0 - psi_a + 2 * psi_a * k / n_tip
        pts.append(pol(ra, t))
    # left flank (descending)
    for r in reversed(flank_r):
        pts.append(pol(r, t0 + half_angle(r)))
    pts.append(pol(rf, t0 + psi_b))
    # root arc to next tooth
    t_a = t0 + psi_b
    t_b = t0 + pitch_ang - psi_b
    for k in range(1, n_root):
        t = t_a + (t_b - t_a) * k / n_root
        pts.append(pol(rf, t))

# remove consecutive duplicates
clean = []
for p in pts:
    if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-6:
        clean.append(p)
if math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) < 1e-6:
    clean.pop()

gear = cq.Workplane("XY").polyline(clean).close().extrude(thickness)
bore = cq.Workplane("XY").circle(bore_d / 2.0).extrude(thickness)
gear = gear.cut(bore)

cq.exporters.export(gear, "out.step")

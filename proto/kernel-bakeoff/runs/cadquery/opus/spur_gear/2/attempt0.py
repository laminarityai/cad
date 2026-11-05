import math
import cadquery as cq

# Gear parameters
z = 24
m = 2.0
pa = math.radians(20.0)
thickness = 10.0
bore_d = 8.0

r = m * z / 2.0            # pitch radius
rb = r * math.cos(pa)      # base radius
ra = r + 1.0 * m           # addendum radius
rf = r - 1.25 * m          # root radius


def inv(a):
    return math.tan(a) - a


def half_angle(rad):
    """Half angular tooth thickness at radius rad (rad >= rb)."""
    a = math.acos(rb / rad)
    return math.pi / (2 * z) + inv(pa) - inv(a)


def polar(rad, ang):
    return (rad * math.cos(ang), rad * math.sin(ang))


n_inv = 20
n_tip = 6
n_root = 8

pts = []
pitch_ang = 2 * math.pi / z
psi_b = half_angle(rb)
psi_a = half_angle(ra)

for i in range(z):
    th = i * pitch_ang

    # Right flank (lower angle side), from root up to tip
    flank = []
    if rf < rb:
        flank.append((rf, psi_b))
    for k in range(n_inv + 1):
        rad = rb + (ra - rb) * k / n_inv
        flank.append((rad, half_angle(rad)))

    for rad, psi in flank:
        pts.append(polar(rad, th - psi))

    # Tip arc (interior points)
    for k in range(1, n_tip):
        a = th - psi_a + 2 * psi_a * k / n_tip
        pts.append(polar(ra, a))

    # Left flank, from tip down to root
    for rad, psi in reversed(flank):
        pts.append(polar(rad, th + psi))

    # Root arc (interior points) to next tooth
    a0 = th + psi_b
    a1 = th + pitch_ang - psi_b
    for k in range(1, n_root):
        a = a0 + (a1 - a0) * k / n_root
        pts.append(polar(rf, a))

# Remove consecutive near-duplicates
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

import math
import cadquery as cq

# Gear parameters
z = 24
m = 2.0
alpha = math.radians(20.0)
thickness = 10.0
bore_d = 8.0

r = m * z / 2.0            # pitch radius
rb = r * math.cos(alpha)   # base radius
ra = r + 1.0 * m           # addendum radius
rf = r - 1.25 * m          # root radius


def inv(a):
    return math.tan(a) - a


def half_angle(rad):
    """Half angular tooth thickness at radius rad (rad >= rb)."""
    ar = math.acos(rb / rad)
    return math.pi / (2 * z) + inv(alpha) - inv(ar)


def polar(rad, ang):
    return (rad * math.cos(ang), rad * math.sin(ang))


n_flank = 20
n_arc = 6
pitch_ang = 2 * math.pi / z
psi_b = half_angle(rb)
psi_a = half_angle(ra)

# Radii along involute flank
r_start = max(rb, rf)
flank_r = [r_start + (ra - r_start) * i / n_flank for i in range(n_flank + 1)]

pts = []
for i in range(z):
    tc = i * pitch_ang
    # Right flank (lower angle side), root -> tip
    if rf < rb:
        pts.append(polar(rf, tc - psi_b))
    for rr in flank_r:
        pts.append(polar(rr, tc - half_angle(rr)))
    # Tip arc
    for k in range(1, n_arc):
        a = tc - psi_a + 2 * psi_a * k / n_arc
        pts.append(polar(ra, a))
    # Left flank, tip -> root
    for rr in reversed(flank_r):
        pts.append(polar(rr, tc + half_angle(rr)))
    if rf < rb:
        pts.append(polar(rf, tc + psi_b))
    # Root arc to next tooth
    a0 = tc + psi_b
    a1 = tc + pitch_ang - psi_b
    for k in range(1, n_arc):
        a = a0 + (a1 - a0) * k / n_arc
        pts.append(polar(rf, a))

gear = (
    cq.Workplane("XY")
    .polyline(pts)
    .close()
    .extrude(thickness)
)

bore = cq.Workplane("XY").circle(bore_d / 2.0).extrude(thickness)
gear = gear.cut(bore)

cq.exporters.export(gear, "out.step")

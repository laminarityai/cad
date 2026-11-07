import math
from build123d import *

# Gear parameters
z = 24
m = 2.0
alpha = math.radians(20.0)
thickness = 10.0
bore_d = 8.0

r = m * z / 2.0            # pitch radius
rb = r * math.cos(alpha)    # base radius
ra = r + m                  # addendum radius
rf = r - 1.25 * m           # root radius


def inv(a):
    return math.tan(a) - a


def half_angle(rad):
    """Half angular tooth thickness at radius rad (rad >= rb)."""
    ar = math.acos(min(1.0, rb / rad))
    return math.pi / (2 * z) + inv(alpha) - inv(ar)


def pol(rad, ang):
    return (rad * math.cos(ang), rad * math.sin(ang))


n_flank = 20
n_tip = 6
n_root = 8

pts = []
pitch_ang = 2 * math.pi / z
for i in range(z):
    tc = i * pitch_ang
    # Flank radii: from root (radial below base circle) up to tip
    r_start = max(rb, rf)
    flank_r = [r_start + (ra - r_start) * k / n_flank for k in range(n_flank + 1)]
    psi_b = half_angle(r_start)

    # Right flank (going up)
    if rf < rb:
        pts.append(pol(rf, tc - psi_b))
    for rr in flank_r:
        pts.append(pol(rr, tc - half_angle(rr)))
    # Tip arc
    psi_a = half_angle(ra)
    for k in range(1, n_tip):
        a = tc - psi_a + 2 * psi_a * k / n_tip
        pts.append(pol(ra, a))
    # Left flank (going down)
    for rr in reversed(flank_r):
        pts.append(pol(rr, tc + half_angle(rr)))
    if rf < rb:
        pts.append(pol(rf, tc + psi_b))
    # Root arc to next tooth
    a0 = tc + psi_b
    a1 = tc + pitch_ang - psi_b
    for k in range(1, n_root):
        a = a0 + (a1 - a0) * k / n_root
        pts.append(pol(rf, a))

wire = Wire.make_polygon([Vector(x, y, 0) for x, y in pts], close=True)
face = Face(wire)
gear = extrude(face, amount=thickness)

bore = Cylinder(bore_d / 2.0, thickness * 3, align=(Align.CENTER, Align.CENTER, Align.CENTER))
gear = gear - bore

if isinstance(gear, Compound) or not isinstance(gear, Solid):
    solids = gear.solids()
    gear = solids[0] if len(solids) == 1 else gear

export_step(gear, "out.step")

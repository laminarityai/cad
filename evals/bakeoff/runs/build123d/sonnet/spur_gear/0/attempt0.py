from build123d import *
import math

z = 24
m = 2.0
pa = math.radians(20)
thickness = 10.0
bore = 8.0

rp = m * z / 2
rb = rp * math.cos(pa)
ra = rp + m
rr = rp - 1.25 * m

def inv(a):
    return math.tan(a) - a

# Involute point at radius r, starting at angle 0 on base circle
def involute_pt(r):
    t = math.sqrt(max((r / rb) ** 2 - 1, 0))
    ang = t - math.atan(t)  # involute polar angle
    return ang

# Half tooth thickness angle at pitch circle = pi/(2z)
# Involute polar angle at pitch radius
phi_p = involute_pt(rp)
# Right flank rotated so that at pitch radius angle = +pi/(2z); left mirrored
r_start = max(rb, rr)
n = 12
radii = [r_start + (ra - r_start) * i / (n - 1) for i in range(n)]

offset = math.pi / (2 * z) - phi_p  # rotate right flank so that tooth centered on x-axis
right = []
left = []
for r in radii:
    a = involute_pt(r)
    th = a + offset  # angle of the flank point (this flank at angle -? )
    # right flank: below axis at base, passes through +pi/(2z)... use mirror symmetry
    right.append((r * math.cos(-th), r * math.sin(-th)))
    left.append((r * math.cos(th), r * math.sin(th)))

# Tooth outline: start at root on right flank, go up right flank to tip, across tip, down left flank
pts = []
# root start points (radial line from root circle to base if root < base)
th0 = (involute_pt(r_start) + offset)
pts_right = right
pts_left = left[::-1]

tooth_pts = []
if rr < rb:
    tooth_pts.append((rr * math.cos(-th0), rr * math.sin(-th0)))
tooth_pts += pts_right
# tip arc midpoint
tip_th = involute_pt(ra) + offset
tooth_pts_tip_mid = (ra, 0)
tooth_pts_left = pts_left
tooth_left_end = None

pitch_ang = 2 * math.pi / z
# Build one tooth sketch face with root-circle-based sector
def rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)

with BuildPart() as gear:
    with BuildSketch() as sk:
        Circle(rr + 0.01)
        for i in range(z):
            a = i * pitch_ang
            with BuildLine() as ln:
                r_pts = [rot(p, a) for p in tooth_pts]
                l_pts = [rot(p, a) for p in tooth_pts_left]
                tip_mid = rot(tooth_pts_tip_mid, a)
                Polyline(*r_pts)
                ThreePointArc(r_pts[-1], tip_mid, l_pts[0])
                Polyline(*l_pts)
                # close back to root circle along radial line
                last = l_pts[-1]
                first = r_pts[0]
                rr_l = rr * 0.9
                p1 = (rr_l * math.cos(math.atan2(last[1], last[0])),
                      rr_l * math.sin(math.atan2(last[1], last[0])))
                p2 = (rr_l * math.cos(math.atan2(first[1], first[0])),
                      rr_l * math.sin(math.atan2(first[1], first[0])))
                Polyline(last, p1, p2, first)
            make_face()
    extrude(amount=thickness)
    with BuildSketch():
        Circle(bore / 2)
    extrude(amount=thickness, mode=Mode.SUBTRACT)

result = gear.part
export_step(result, "out.step")

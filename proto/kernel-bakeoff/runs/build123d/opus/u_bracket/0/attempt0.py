from build123d import *

W, H, D, T = 40.0, 30.0, 50.0, 2.0
FILLET_R = 2.0
HOLE_D = 6.0
HOLE_Z = 20.0

with BuildPart() as bracket:
    with BuildSketch(Plane.XZ) as profile:
        Rectangle(W, H, align=(Align.CENTER, Align.MIN))
        with Locations((0, T)):
            Rectangle(W - 2 * T, H + 5, align=(Align.CENTER, Align.MIN), mode=Mode.SUBTRACT)
        inner_corners = [
            v for v in profile.vertices()
            if abs(v.Z - T) < 1e-4 and abs(abs(v.X) - (W / 2 - T)) < 1e-4
        ]
        fillet(inner_corners, radius=FILLET_R)
    extrude(amount=D / 2, both=True)

    # Coaxial through holes in both side walls
    with Locations(Location((0, 0, HOLE_Z), (0, 90, 0))):
        Cylinder(HOLE_D / 2, W + 10, mode=Mode.SUBTRACT)

result = bracket.part
export_step(result, "out.step")

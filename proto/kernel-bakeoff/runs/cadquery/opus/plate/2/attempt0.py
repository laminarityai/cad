import cadquery as cq

L, W, T = 100.0, 50.0, 6.0
hole_d = 5.1
inset = 8.0

pts = [
    (-L / 2 + inset, -W / 2 + inset),
    (L / 2 - inset, -W / 2 + inset),
    (L / 2 - inset, W / 2 - inset),
    (-L / 2 + inset, W / 2 - inset),
]

plate = (
    cq.Workplane("XY")
    .box(L, W, T)
    .faces(">Z")
    .workplane()
    .pushPoints(pts)
    .hole(hole_d)
)

cq.exporters.export(plate, "out.step")

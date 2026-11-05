import cadquery as cq

L, W, T = 100.0, 50.0, 6.0
d = 5.1
inset = 8.0

plate = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))

pts = [
    (L / 2 - inset, W / 2 - inset),
    (-(L / 2 - inset), W / 2 - inset),
    (L / 2 - inset, -(W / 2 - inset)),
    (-(L / 2 - inset), -(W / 2 - inset)),
]

plate = (
    plate.faces(">Z").workplane(centerOption="CenterOfBoundBox")
    .pushPoints(pts)
    .hole(d)
)

cq.exporters.export(plate, "out.step")

import cadquery as cq

L, W, T = 100.0, 50.0, 6.0
d = 5.1
inset = 8.0

plate = (
    cq.Workplane("XY")
    .box(L, W, T, centered=(True, True, False))
    .faces(">Z")
    .workplane()
    .rect(L - 2 * inset, W - 2 * inset, forConstruction=True)
    .vertices()
    .hole(d)
)

cq.exporters.export(plate, "out.step")

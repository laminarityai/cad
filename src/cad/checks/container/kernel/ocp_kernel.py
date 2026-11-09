import tempfile
from pathlib import Path
from typing import cast

from cad.checks.container.kernel.ocp_handles import Movable, Ocp, Xyz, load_ocp
from cad.checks.container.kernel.protocol import (
    Curved,
    EdgeUses,
    FaceInfo,
    Flat,
    Inertia,
    Kernel,
    Point,
    Round,
    Shape,
    StepTooLarge,
    Surface,
    Unreadable,
    VolumeProps,
    first_line,
)
from cad.checks.container.vectors import cross, unit

STEP_TIME_STAMP = "2000-01-01T00:00:00"
STEP_SCHEMA = "AP214IS"


class OcpKernel:
    def __init__(self) -> None:
        self._ocp = load_ocp()
        self._wrote_step = False

    def read_brep(self, data: bytes) -> Shape | Unreadable:
        if not data:
            return Unreadable("the BREP is empty")
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "variant.brep"
                path.write_bytes(data)
                shape = self._ocp.new_shape()
                read = self._ocp.brep_tools.Read_s(shape, str(path), self._ocp.new_builder())
        except Exception as error:
            return Unreadable(f"{type(error).__name__}: {first_line(str(error))}")
        if not read or shape.IsNull():
            return Unreadable(f"BRepTools.Read_s rejected {len(data)} bytes as not a BREP file")
        return shape

    def solids(self, shape: Shape) -> tuple[Shape, ...]:
        ocp = self._ocp
        return tuple(map(ocp.topods.Solid_s, self._explore(shape, ocp.solid, ocp.any_shape)))

    def outside_solids(self, shape: Shape) -> int:
        ocp = self._ocp
        nesting = (
            (ocp.shell, ocp.solid),
            (ocp.face, ocp.shell),
            (ocp.edge, ocp.face),
            (ocp.vertex, ocp.edge),
        )
        return sum(len(self._explore(shape, kind, container)) for kind, container in nesting)

    def _explore(self, shape: Shape, kind: object, avoid: object) -> list[Shape]:
        found: list[Shape] = []
        explorer = self._ocp.new_explorer(shape, kind, avoid)
        while explorer.More():
            found.append(explorer.Current())
            explorer.Next()
        return found

    def is_valid(self, shape: Shape) -> bool:
        return self._ocp.new_analyzer(shape).IsValid()

    def edge_uses(self, shape: Shape) -> EdgeUses:
        ocp = self._ocp
        edges = ocp.new_ancestor_map()
        ocp.topexp.MapShapesAndAncestors_s(shape, ocp.edge, ocp.face, edges)
        free = over_used = 0
        for index in range(1, edges.Extent() + 1):
            if ocp.brep_tool.Degenerated_s(ocp.topods.Edge_s(edges.FindKey(index))):
                continue
            uses = edges.FindFromIndex(index).Extent()
            free += uses == 1
            over_used += uses > 2
        return EdgeUses(free, over_used)

    def volume_props(self, shape: Shape) -> VolumeProps:
        props = self._ocp.new_props()
        self._ocp.brep_gprop.VolumeProperties_s(shape, props)
        center = props.CentreOfMass()
        return VolumeProps(props.Mass(), (center.X(), center.Y(), center.Z()))

    def bounds(self, shape: Shape) -> tuple[Point, Point] | None:
        box = self._ocp.new_box()
        self._ocp.brep_bnd_lib.AddOptimal_s(
            shape, box, useTriangulation=False, useShapeTolerance=False
        )
        if box.IsVoid() or box.IsOpen():
            return None
        x0, y0, z0, x1, y1, z1 = box.Get()
        return (x0, y0, z0), (x1, y1, z1)

    def extents(self, shape: Shape) -> tuple[float, float, float] | None:
        corners = self.bounds(shape)
        if corners is None:
            return None
        low, high = corners
        return (high[0] - low[0], high[1] - low[1], high[2] - low[2])

    def max_tolerance(self, shape: Shape) -> float:
        return self._ocp.new_tolerance().Tolerance(shape, 1)

    def faces(self, shape: Shape) -> tuple[FaceInfo, ...]:
        ocp = self._ocp
        found = self._explore(shape, ocp.face, ocp.any_shape)
        return tuple(_face_info(ocp, ocp.topods.Face_s(face)) for face in found)

    def inertia(self, shape: Shape) -> Inertia:
        ocp = self._ocp
        props = ocp.new_props()
        ocp.brep_gprop.VolumeProperties_s(shape, props)
        center = _coords(props.CentreOfMass())
        principal = props.PrincipalProperties()
        first = _coords(principal.FirstAxisOfInertia())
        second = _coords(principal.SecondAxisOfInertia())
        axes = (first, second, cross(first, second))
        frame = ocp.new_frame(
            ocp.new_point(*center), ocp.new_direction(*axes[2]), ocp.new_direction(*axes[0])
        )
        trsf = ocp.new_trsf()
        trsf.SetTransformation(frame)
        local = cast(Movable, shape).Moved(ocp.new_location(trsf))
        box = ocp.new_box()
        ocp.brep_bnd_lib.AddOptimal_s(local, box, useTriangulation=False, useShapeTolerance=False)
        x0, y0, z0, x1, y1, z1 = box.Get()
        return Inertia(
            volume=props.Mass(),
            center=center,
            axes=axes,
            moments=principal.Moments(),
            spans=((x0, x1), (y0, y1), (z0, z1)),
        )

    def common_volume(self, first: Shape, second: Shape) -> float | None:
        common = self._ocp.new_common(first, second)
        return self.volume_props(common.Shape()).volume if common.IsDone() else None

    def min_distance(self, first: Shape, second: Shape) -> float | None:
        ocp = self._ocp
        tool = ocp.new_distance()
        tool.LoadS1(first)
        tool.LoadS2(second)
        tool.SetFlag(ocp.extrema_min)
        tool.SetAlgo(ocp.extrema_grad)
        # Issue #92 measured multithreading 1.8 to 3.6 times slower on large parts.
        tool.SetMultiThread(False)
        tool.Perform()
        return tool.Value() if tool.IsDone() else None

    def step_bytes(self, shape: Shape, cap: int) -> bytes | StepTooLarge:
        if self._wrote_step:
            raise RuntimeError("one container writes one STEP")
        self._wrote_step = True
        ocp = self._ocp
        ocp.interface_static.SetCVal_s("write.step.schema", STEP_SCHEMA)
        writer = ocp.new_writer()
        transferred = writer.Transfer(shape, ocp.as_is)
        # The default header holds the clock, so two runs would differ.
        header = ocp.new_header(writer.Model())
        header.SetTimeStamp(ocp.new_hstring(STEP_TIME_STAMP))
        header.SetName(ocp.new_hstring("result"))
        header.SetAuthorValue(1, ocp.new_hstring(""))
        header.SetOrganizationValue(1, ocp.new_hstring(""))
        header.SetOriginatingSystem(ocp.new_hstring("cad"))
        header.SetAuthorisation(ocp.new_hstring(""))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.step"
            if transferred != ocp.ret_done or writer.Write(str(path)) != ocp.ret_done:
                raise RuntimeError("STEPControl_Writer could not write the shape")
            size = path.stat().st_size
            return StepTooLarge(size) if size > cap else path.read_bytes()


def _coords(point: Xyz) -> Point:
    return (point.X(), point.Y(), point.Z())


def _face_info(ocp: Ocp, face: Shape) -> FaceInfo:
    props = ocp.new_props()
    ocp.brep_gprop.SurfaceProperties_s(face, props)
    return FaceInfo(_surface(ocp, face), props.Mass(), _coords(props.CentreOfMass()))


def _surface(ocp: Ocp, face: Shape) -> Surface:
    u0, u1, v0, v1 = ocp.brep_tools.UVBounds_s(face)
    point, normal = ocp.new_point(0, 0, 0), ocp.new_vector(0, 0, 0)
    ocp.new_face_props(face).Normal((u0 + u1) / 2, (v0 + v1) / 2, point, normal)
    outward = unit(_coords(normal))
    adaptor = ocp.new_adaptor(face)
    kind = adaptor.GetType()
    if kind == ocp.plane:
        return Flat(outward)
    if kind != ocp.cylinder:
        return Curved()
    cylinder = adaptor.Cylinder()
    origin = _coords(cylinder.Position().Location())
    axis = _coords(cylinder.Position().Direction())
    v = (v0 + v1) / 2
    on_axis = (origin[0] + v * axis[0], origin[1] + v * axis[1], origin[2] + v * axis[2])
    radial = tuple(p - a for p, a in zip(_coords(point), on_axis, strict=True))
    concave = sum(n * r for n, r in zip(outward, radial, strict=True)) < 0
    return Round(origin, axis, cylinder.Radius(), v0, v1, u1 - u0, concave)


def ocp_kernel() -> Kernel:
    return OcpKernel()

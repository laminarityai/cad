from __future__ import annotations

import importlib
import io
import json
import os
import resource
import runpy
import sys
import traceback
from base64 import b64encode
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from types import TracebackType

    from cad.sandbox.wire import AreaReport, FailedReport, PartListing, Report

VARIANT = Path("/tmp/variant.py")
PARTS = Path("/tmp/parts")
CPU_KILL_AFTER_SECONDS = 5
FUSED_SHARE = 0.5
AREAS = "areas"
UNNAMED = "unnamed"


class Build123d(Protocol):
    Shape: type[object]

    def export_brep(self, to_export: object, file_path: io.BytesIO) -> bool: ...


class Coloured(Protocol):
    def faces(self) -> Sequence[object]: ...


class Wrapped(Protocol):
    @property
    def wrapped(self) -> object: ...


class Solid(Protocol):
    def IsPartner(self, other: Solid) -> bool: ...


def main() -> None:
    root = os.getpid()
    report_channel = os.dup(1)
    os.dup2(2, 1)
    report = run_variant(root, int(sys.argv[1]), json.loads(sys.argv[2]))
    sys.stdout.flush()
    sys.stderr.flush()
    with os.fdopen(report_channel, "wb") as channel:
        channel.write(json.dumps(report).encode())
    # Skips interpreter shutdown, so the variant's atexit hooks and threads never run after this.
    os._exit(0)


def run_variant(root: int, cpu_seconds: int, listed: list[PartListing]) -> Report:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + CPU_KILL_AFTER_SECONDS))
        helpers = unpack(sys.stdin.buffer.read(), listed)
        namespace = runpy.run_path(str(VARIANT), init_globals=helpers, run_name="__main__")
    except BaseException as error:
        exit_if_forked_child(root)
        return failed(error)
    exit_if_forked_child(root)
    try:
        return result_report(namespace, listed)
    except BaseException as error:
        return failed(error)


def unpack(sent: bytes, listed: list[PartListing]) -> dict[str, object]:
    """Write the code, and each supplied part's BREP that follows it on stdin, and give the code
    `part` and `placed` to read them with."""
    start = len(sent) - sum(one["size"] for one in listed)
    VARIANT.write_bytes(sent[:start])
    paths: dict[str, Path] = {}
    for index, one in enumerate(listed):
        PARTS.mkdir(exist_ok=True)
        paths[one["id"]] = part_path(index)
        paths[one["id"]].write_bytes(sent[start : start + one["size"]])
        start += one["size"]
    placements = {one["id"]: one["placements"] for one in listed}

    def sent_part(part_id: str) -> Path:
        if part_id not in paths:
            raise ValueError(f"{part_id!r} is not a part this build reads; name it in parts")
        return paths[part_id]

    def part(part_id: str) -> object:
        """The supplied part's solids, in the part's own frame."""
        return importlib.import_module("build123d").import_brep(str(sent_part(part_id)))

    def placed(part_id: str) -> list[object]:
        """A build123d Location for each placement of the part that the build names."""
        sent_part(part_id)
        location = importlib.import_module("build123d").Location
        return [location(tuple(p["at"]), tuple(p["rotate"])) for p in placements[part_id]]

    return {"part": part, "placed": placed}


def part_path(index: int) -> Path:
    return PARTS / f"{index}.brep"


def exit_if_forked_child(root: int) -> None:
    if os.getpid() != root:
        os._exit(0)


def result_report(namespace: dict[str, object], listed: list[PartListing]) -> Report:
    if "result" not in namespace:
        return {"kind": "no_result"}
    shape = namespace["result"]
    build123d = cast(Build123d, importlib.import_module("build123d"))
    if not isinstance(shape, build123d.Shape):
        return {"kind": "not_a_shape", "found": utf8(type(shape).__name__)}
    fused = fused_part(cast(Wrapped, shape), listed)
    if fused is not None:
        return {"kind": "build_failed", "error": fused, "traceback": ""}
    brep = io.BytesIO()
    if not build123d.export_brep(shape, brep):
        raise RuntimeError("build123d could not export `result` as BREP")
    painted = areas(cast(Coloured, shape), namespace)
    named = bodies(shape)
    return {
        "kind": "built",
        "brep": b64encode(brep.getvalue()).decode(),
        "areas": painted,
        "bodies": named,
    }


def fused_part(shape: Wrapped, listed: list[PartListing]) -> str | None:
    """Why `result` cannot stand when it holds most of a supplied part, in the part's own frame or
    at one of its placements. That is a copy fused into it by mistake, and every check would grade
    it as the agent's body (ADR-0012). A copy the kernel cannot intersect is let through."""
    build123d = importlib.import_module("build123d")
    for index, one in enumerate(listed):
        read: Wrapped = build123d.import_brep(str(part_path(index)))
        copies = [("in its own frame", read)]
        for number, spot in enumerate(one["placements"], 1):
            where = "at placement {} ({:g}, {:g}, {:g})".format(number, *spot["at"])
            at = build123d.Location(tuple(spot["at"]), tuple(spot["rotate"]))
            copies.append((where, cast(Wrapped, at * read)))
        for where, copy in copies:
            share = held_share(shape, copy)
            if share > FUSED_SHARE:
                return utf8(
                    f"result holds {min(share, 1):.0%} of supplied part {one['id']} {where}. "
                    "result is your body only, and every check grades it, so the checks would "
                    "grade the person's part as yours. Keep the part out of result, and use it "
                    "to shape your body, such as a pocket around it."
                )
    return None


def held_share(shape: Wrapped, copy: Wrapped) -> float:
    """The share of the copy's volume that `shape` holds, 0 when their bounding boxes miss."""
    try:
        whole = volume_of(cast(Solid, copy.wrapped))
        if whole <= 0 or apart(shape, copy):
            return 0.0
        common = importlib.import_module("OCP.BRepAlgoAPI").BRepAlgoAPI_Common(
            shape.wrapped, copy.wrapped
        )
        return volume_of(common.Shape()) / whole if common.IsDone() else 0.0
    except Exception:
        return 0.0


def apart(one: Wrapped, other: Wrapped) -> bool:
    bounds, add = importlib.import_module("OCP.Bnd"), importlib.import_module("OCP.BRepBndLib")
    boxes = [bounds.Bnd_Box(), bounds.Bnd_Box()]
    for shape, box in zip((one, other), boxes, strict=True):
        add.BRepBndLib.Add_s(shape.wrapped, box)
    return bool(boxes[0].IsOut(boxes[1]))


def bodies(shape: object) -> list[str | None] | str:
    """The name of each solid of `shape`, numbered by the kernel's explorer as the checks number
    them: the `label` of its nearest labelled node in the `children` tree, or None. A label in
    the `areas` list never names a body. Empty for one solid or none, which is one unnamed body
    whatever its label says."""
    try:
        every = solids_of(shape)
        if len(every) <= 1:
            return []
        named: list[str | None] = []
        for node, label in tree(shape):
            if getattr(node, "children", ()):
                continue
            for solid in solids_of(node):
                if len(named) == len(every) or not alike(every[len(named)], solid):
                    raise ValueError("the solids of the children tree are not those of `result`")
                named.append(label or None)
        if len(named) != len(every):
            raise ValueError("the children tree holds fewer solids than `result`")
        return named
    except Exception as error:
        return utf8(f"{type(error).__name__}: {error}")


def alike(solid: Solid, other: Solid) -> bool:
    """A moved Compound keeps its children where they were, so a solid and the child it came
    from can differ in place but never in volume."""
    if solid.IsPartner(other):
        return True
    one, two = volume_of(solid), volume_of(other)
    return abs(one - two) <= 1e-6 * max(abs(one), abs(two))


def volume_of(solid: Solid) -> float:
    props = importlib.import_module("OCP.GProp").GProp_GProps()
    importlib.import_module("OCP.BRepGProp").BRepGProp.VolumeProperties_s(solid, props)
    return float(props.Mass())


def solids_of(shape: object) -> list[Solid]:
    explorers = importlib.import_module("OCP.TopExp")
    kinds = importlib.import_module("OCP.TopAbs")
    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None:
        return []
    explorer = explorers.TopExp_Explorer(wrapped, kinds.TopAbs_SOLID)
    found: list[Solid] = []
    while explorer.More():
        found.append(explorer.Current())
        explorer.Next()
    return found


def areas(shape: Coloured, namespace: dict[str, object]) -> list[AreaReport] | str:
    """The faces of `shape` that the code coloured, by the kernel's `color` and `label` on a
    shape the module keeps whose faces are still the result's, on the shape, on each child of a
    Compound, and on each shape in a list named `areas`, which is how a set of faces gets a
    colour: a face object from `faces()` is new on every call, so a colour set on one is gone.
    A later, nearer one wins, and faces are numbered as `faces()` numbers them, which is the
    order the BREP keeps. `Compound([a, b])` keeps the faces of `a` and `b` but not their
    colours, so the module's own `a` and `b` give them back. A node of the tree is named as its
    body is, since a child takes its parent's colour but not its label."""
    try:
        listed = namespace.get(AREAS, ())
        named = cast(Iterable[object], listed) if isinstance(listed, list | tuple) else ()
        kept = [one for one in namespace.values() if not isinstance(one, type) and one is not shape]
        number = {face: index for index, face in enumerate(shape.faces())}
        painted: dict[int, tuple[str, str]] = {}
        before = [(one, label_of(one)) for one in kept]
        after = [(one, label_of(one)) for one in named]
        for one, label in [*before, *tree(shape), *after]:
            colour: object = getattr(one, "color", None)
            if colour is None or not callable(getattr(one, "faces", None)):
                continue
            look = (label or UNNAMED, hex_of(colour))
            for face in cast(Coloured, one).faces():
                if face in number:
                    painted[number[face]] = look
        grouped: dict[tuple[str, str], list[int]] = {}
        for index in sorted(painted):
            grouped.setdefault(painted[index], []).append(index)
        return [{"name": n, "colour": c, "faces": f} for (n, c), f in grouped.items()]
    except Exception as error:
        return utf8(f"{type(error).__name__}: {error}")


def tree(shape: object) -> list[tuple[object, str]]:
    """`shape` and each node of its `children` tree, in order, with the label of its nearest
    labelled node, itself included, or "" when none is."""
    found: list[tuple[object, str]] = []
    pending: list[tuple[object, str]] = [(shape, "")]
    while pending:
        node, inherited = pending.pop()
        label = label_of(node) or inherited
        found.append((node, label))
        children = list(cast(Iterable[object], getattr(node, "children", ())))
        pending.extend((child, label) for child in reversed(children))
    return found


def label_of(node: object) -> str:
    return utf8(str(getattr(node, "label", "") or ""))


def hex_of(colour: object) -> str:
    parts = tuple(cast(Iterable[float], colour))[:3]
    red, green, blue = (min(max(round(float(part) * 255), 0), 255) for part in parts)
    return f"#{red:02x}{green:02x}{blue:02x}"


def failed(error: BaseException) -> FailedReport:
    lines = traceback.format_exception(type(error), error, variant_frames(error.__traceback__))
    summary = traceback.format_exception_only(error)
    # format_exception_only puts one entry per note after the "Type: message" entry.
    notes = getattr(error, "__notes__", ())
    return {
        "kind": "build_failed",
        "error": utf8(summary[-1 - len(notes)].strip()),
        "traceback": utf8("".join(lines)),
    }


def utf8(text: str) -> str:
    """The host rejects JSON holding a lone surrogate, so the report must not carry one."""
    return text.encode("utf-8", "replace").decode("utf-8")


def variant_frames(frames: TracebackType | None) -> TracebackType | None:
    while frames is not None and frames.tb_frame.f_code.co_filename != str(VARIANT):
        frames = frames.tb_next
    return frames


if __name__ == "__main__":
    main()

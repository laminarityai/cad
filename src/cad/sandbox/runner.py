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

    from cad.sandbox.wire import AreaReport, FailedReport, Report

VARIANT = Path("/tmp/variant.py")
CPU_KILL_AFTER_SECONDS = 5
AREAS = "areas"
UNNAMED = "unnamed"


class Build123d(Protocol):
    Shape: type[object]

    def export_brep(self, to_export: object, file_path: io.BytesIO) -> bool: ...


class Coloured(Protocol):
    def faces(self) -> Sequence[object]: ...


class Solid(Protocol):
    def IsPartner(self, other: Solid) -> bool: ...


def main() -> None:
    root = os.getpid()
    report_channel = os.dup(1)
    os.dup2(2, 1)
    report = run_variant(root, int(sys.argv[1]))
    sys.stdout.flush()
    sys.stderr.flush()
    with os.fdopen(report_channel, "wb") as channel:
        channel.write(json.dumps(report).encode())
    # Skips interpreter shutdown, so the variant's atexit hooks and threads never run after this.
    os._exit(0)


def run_variant(root: int, cpu_seconds: int) -> Report:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + CPU_KILL_AFTER_SECONDS))
        VARIANT.write_bytes(sys.stdin.buffer.read())
        namespace = runpy.run_path(str(VARIANT), run_name="__main__")
    except BaseException as error:
        exit_if_forked_child(root)
        return failed(error)
    exit_if_forked_child(root)
    try:
        return result_report(namespace)
    except BaseException as error:
        return failed(error)


def exit_if_forked_child(root: int) -> None:
    if os.getpid() != root:
        os._exit(0)


def result_report(namespace: dict[str, object]) -> Report:
    if "result" not in namespace:
        return {"kind": "no_result"}
    shape = namespace["result"]
    build123d = cast(Build123d, importlib.import_module("build123d"))
    if not isinstance(shape, build123d.Shape):
        return {"kind": "not_a_shape", "found": utf8(type(shape).__name__)}
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

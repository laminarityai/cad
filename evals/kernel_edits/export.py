"""Run model scripts and export each one's `result` to STEP, in either library's env.

The contract matches the sandbox: a script assigns its final shape to `result`. For an
assembly, `result` is a list with one shape per part. This file imports neither
build123d nor CadQuery, so the same exporter writes both libraries' STEP files.

Usage: export.py OUT_DIR SCRIPT...  writes OUT_DIR/<script stem>.step for each script.
"""

import runpy
import sys
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.IFSelect import IFSelect_RetDone
from OCP.Message import Message, Message_Gravity
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape


def occ_shapes(value: object) -> list[TopoDS_Shape]:
    """The OCCT shapes inside a build123d or CadQuery result, in order."""
    if isinstance(value, TopoDS_Shape):
        return [value]
    if isinstance(value, list | tuple):
        items: list[object] = list(value)  # pyright: ignore[reportUnknownArgumentType]
        return [shape for item in items for shape in occ_shapes(item)]
    if callable(to_compound := getattr(value, "toCompound", None)):
        return occ_shapes(to_compound())
    if callable(vals := getattr(value, "vals", None)):
        return occ_shapes(vals())
    wrapped: object = getattr(value, "wrapped", None)
    if isinstance(wrapped, TopoDS_Shape):
        return [wrapped]
    raise TypeError(f"result holds a {type(value).__name__}, which is not a shape")


def result_of(script: Path) -> list[TopoDS_Shape]:
    names = runpy.run_path(str(script), run_name="__main__")
    if "result" not in names:
        raise NameError(f"{script} does not assign `result`")
    return occ_shapes(names["result"])


def quiet_occt() -> None:
    """Stop OCCT printing transfer statistics to stdout on every STEP write."""
    printers = Message.DefaultMessenger_s().Printers()
    for i in range(1, printers.Size() + 1):
        printers.Value(i).SetTraceLevel(Message_Gravity.Message_Fail)


def write_step(shapes: list[TopoDS_Shape], path: Path) -> None:
    quiet_occt()
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise OSError(f"could not write {path}")


def main(argv: list[str]) -> int:
    out_dir = Path(argv[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    for script in map(Path, argv[1:]):
        write_step(result_of(script), out_dir / f"{script.stem}.step")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

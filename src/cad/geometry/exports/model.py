from typing import Annotated, Literal

from pydantic import Field

from cad.errors import NotFound
from cad.frozen import Frozen

type ExportFormat = Literal["step", "stl", "3mf"]


class UnknownExport(NotFound):
    pass


class Exported(Frozen):
    """The STEP, STL and 3MF of one BREP are stored beside this record. `key` names what was
    exported: the BREP's sha256, or with the areas the build code coloured, a sha256 of both.
    `colours_left_out` says why the STEP was written without them, when it was."""

    kind: Literal["exported"] = "exported"
    key: str
    version: str
    colours_left_out: str | None = None


class ExportFailed(Frozen):
    kind: Literal["failed"] = "failed"
    key: str
    version: str
    reason: str


class ExportPending(Frozen):
    kind: Literal["pending"] = "pending"
    key: str


type Stored = Annotated[Exported | ExportFailed, Field(discriminator="kind")]
type ExportRead = Annotated[Exported | ExportFailed | ExportPending, Field(discriminator="kind")]

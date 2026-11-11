from typing import Annotated, Literal

from pydantic import Field

from cad.errors import NotFound
from cad.frozen import Frozen

type ExportFormat = Literal["step", "stl", "3mf"]


class UnknownExport(NotFound):
    pass


class Exported(Frozen):
    """The STEP, STL and 3MF of one BREP are stored beside this record."""

    kind: Literal["exported"] = "exported"
    brep_sha256: str
    version: str


class ExportFailed(Frozen):
    kind: Literal["failed"] = "failed"
    brep_sha256: str
    version: str
    reason: str


class ExportPending(Frozen):
    kind: Literal["pending"] = "pending"
    brep_sha256: str


type Stored = Annotated[Exported | ExportFailed, Field(discriminator="kind")]
type ExportRead = Annotated[Exported | ExportFailed | ExportPending, Field(discriminator="kind")]

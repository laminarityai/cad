import re
from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, StringConstraints

from cad.briefs import store as briefs
from cad.geometry import store as meshes
from cad.geometry.exports import job, store
from cad.geometry.exports.lane import EXPORTS, key_of
from cad.geometry.exports.model import Exported, ExportFailed, ExportFormat, UnknownExport
from cad.operations.model import Audience, Download, Input, Tenant, operation
from cad.sandbox import image
from cad.variant_sets import store as variant_sets
from cad.variants import entry

EXPORT = (
    "Starts and reads the download of one revision of an option as STEP, STL or 3MF. The analysis "
    "image writes the three files once per BREP, in the background. Returns ready with the url "
    "to fetch the file from and the file name it is saved under, pending while the job runs: "
    "ask again, or failed with the reason. The file is the BREP the checks measured, in "
    "millimetres. The STEP carries the colours the build code gave its areas; the STL and 3MF "
    "carry none. When the coloured STEP could not be written, the plain one is served and "
    "colours_left_out on the STEP says why."
)
EXPORT_FILE = (
    "One exported file of one BREP, with the colours its build code set, made by one export job "
    "version, sent as an attachment. The key and the version name the bytes, so a client may "
    "cache them for good. A version that is no longer current, or a key that was not exported, "
    "is not found, so take the URL from the export. "
    "`name` is the file name without its extension, cleaned to lowercase letters, digits and "
    "dashes."
)
EXPORT_PATH: Final = "/v1/exports/{version}/{key}.{format}"
UNNAMED: Final = "part"
NOT_ALNUM: Final = re.compile(r"[^a-z0-9]+")


class ExportInput(Input):
    variant_id: str
    brief_id: str
    format: ExportFormat


class ExportFileInput(Input):
    version: Annotated[str, Field(pattern=r"^[0-9a-f]{12}$")]
    key: Annotated[str, Field(pattern=meshes.SHA256.pattern)]
    format: ExportFormat
    name: Annotated[str, StringConstraints(max_length=200)] = UNNAMED


class ExportReady(BaseModel):
    kind: Literal["ready"] = "ready"
    url: str
    filename: str
    colours_left_out: str | None = Field(default=None, exclude_if=lambda why: why is None)


class ExportPreparing(BaseModel):
    kind: Literal["pending"] = "pending"


class ExportFailure(BaseModel):
    kind: Literal["failed"] = "failed"
    reason: str


type ExportView = Annotated[
    ExportReady | ExportPreparing | ExportFailure, Field(discriminator="kind")
]


def slug(text: str) -> str:
    return NOT_ALNUM.sub("-", text.lower()).strip("-") or UNNAMED


def stem_of(tenant: Tenant, brief_id: str, variant_id: str) -> str:
    """`{brief name}-{option label}-rev{n}`: what the page shows for the revision, from the brief's
    variant set. A variant that is no revision of the brief is refused."""
    brief = briefs.read_brief(tenant.roots, brief_id)
    key = variant_sets.set_key(tenant.roots, brief_id)
    tag = image.image_tag(image.BUILD)
    for member in variant_sets.members(tenant.roots.projects, key):
        for number, revision in enumerate(member.revisions, start=1):
            if variant_id in (revision.built_as, revision.live_id(tag)):
                option = member.latest.option
                label = f"option {member.slot}" if option is None else option.label
                return slug(f"{brief.name or UNNAMED} {label} rev{number}")
    raise entry.UnknownVariant(f"variant {variant_id} is no revision of brief {brief_id}")


def export(tenant: Tenant, arguments: ExportInput) -> ExportView:
    held = entry.open_entry(tenant.variants, arguments.variant_id, image.image_tag(image.BUILD))
    stem = stem_of(tenant, arguments.brief_id, held.id)
    read = EXPORTS.read(tenant.geometry, held)
    if isinstance(read, ExportFailed):
        return ExportFailure(reason=read.reason)
    if not isinstance(read, Exported):
        return ExportPreparing()
    path = EXPORT_PATH.format(version=job.VERSION, key=key_of(held), format=arguments.format)
    left_out = read.colours_left_out if arguments.format == "step" else None
    return ExportReady(
        url=f"{path}?name={stem}", filename=f"{stem}.{arguments.format}", colours_left_out=left_out
    )


def export_file(tenant: Tenant, arguments: ExportFileInput) -> Download:
    stored = store.read(tenant.geometry, arguments.key)
    data = store.read_file(tenant.geometry, arguments.key, arguments.format)
    if not isinstance(stored, Exported) or arguments.version != job.VERSION or data is None:
        raise UnknownExport(
            f"no {arguments.format} of export job {arguments.version} is stored "
            f"for key {arguments.key}"
        )
    return Download(filename=f"{slug(arguments.name)}.{arguments.format}", data=data)


OPERATIONS: Final = (
    operation(
        name="export",
        audience=Audience.PERSON,
        description=EXPORT,
        input=ExportInput,
        output=ExportView,
        run=export,
    ),
    operation(
        name="export_file",
        audience=Audience.PERSON,
        description=EXPORT_FILE,
        input=ExportFileInput,
        output=Download,
        run=export_file,
    ),
)

from typing import Final

from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import GeometryRead
from cad.operations.model import Audience, Input, Tenant, operation
from cad.sandbox import image
from cad.variants import entry

GEOMETRY = (
    "The mesh of one built variant, in three-cad-viewer's shapes format, for the viewer. The "
    "analysis image tessellates the BREP the checks measure, in the background, once per BREP. "
    "Returns tessellated with the shapes, failed with the reason, or pending while the job runs: "
    "read it again for the mesh. Each result names the BREP's sha256, which identifies it."
)


class GeometryInput(Input):
    variant_id: str


def geometry(tenant: Tenant, arguments: GeometryInput) -> GeometryRead:
    held = entry.open_entry(tenant.variants, arguments.variant_id, image.image_tag(image.BUILD))
    return TESSELLATIONS.read(tenant.geometry, held)


OPERATIONS: Final = (
    operation(
        name="geometry",
        audience=Audience.PERSON,
        description=GEOMETRY,
        input=GeometryInput,
        output=GeometryRead,
        run=geometry,
    ),
)

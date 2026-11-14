from typing import Final

from pydantic import BaseModel

from cad.operations.model import Audience, Input, Tenant, operation
from cad.operations.scorecards import ScoreVariantInput, score_variant

REBUILD_VARIANT: Final = (
    "Rebuild an option that an earlier version of the app stored, and score it again, from its "
    "stored and signed code only. It is the path score_variant takes for such a variant, with "
    "the material and requirements of the brief. It changes no check, table or requirement."
)


class RebuildInput(Input):
    variant_id: str
    brief_id: str


class Rebuilt(BaseModel):
    variant_id: str
    rebuilt_from: str | None


def rebuild_variant(tenant: Tenant, arguments: RebuildInput) -> Rebuilt:
    card = score_variant(
        tenant, ScoreVariantInput(variant_id=arguments.variant_id, brief_id=arguments.brief_id)
    )
    return Rebuilt(variant_id=card.variant_id, rebuilt_from=card.rebuilt_from)


OPERATIONS: Final = (
    operation(
        name="rebuild_variant",
        audience=Audience.PERSON,
        description=REBUILD_VARIANT,
        input=RebuildInput,
        output=Rebuilt,
        run=rebuild_variant,
    ),
)

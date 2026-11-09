from typing import Annotated, Final

from pydantic import BaseModel, Field

from cad.briefs.model import MAX_STATEMENT_CHARS
from cad.context_parts import store
from cad.context_parts.ingest import Facts
from cad.context_parts.model import MAX_NAME_CHARS, Outcome
from cad.operations.model import Audience, Input, Tenant, operation

PROPOSE_CONTEXT_PART = (
    "Propose a context part: a part the user's new part must fit with, such as a rail it slides "
    "onto or a housing it sits in. Propose one when the brief says the part must fit with an "
    "existing part. Today the part is a variant you built: pass its variant_id, a short name, "
    "the brief_id and a quote copied exactly from the brief that names the part. The server "
    "reads the variant's geometry and returns the part_id, its status and its facts: the number "
    "of solids, the volume in mm^3 and the bounding box in mm. The box is in the part's own "
    "frame, so build the new part in that same frame. The facts help you build in the right "
    "place, and no check reads them. Proposing never confirms: the user confirms the part on "
    "the ask_to_confirm page, with the requirements. Proposing the same part again returns it "
    "while it waits or is confirmed. After the user declines it, proposing it again asks again."
)


class PartProposed(BaseModel):
    part_id: str
    status: Outcome
    facts: Facts


class ProposeContextPartInput(Input):
    brief_id: str
    quote: Annotated[str, Field(min_length=1, max_length=MAX_STATEMENT_CHARS)]
    name: Annotated[str, Field(min_length=1, max_length=MAX_NAME_CHARS)]
    variant_id: str


def propose_context_part(tenant: Tenant, arguments: ProposeContextPartInput) -> PartProposed:
    part = store.propose(
        tenant.roots,
        tenant.variants,
        arguments.brief_id,
        arguments.quote,
        arguments.name,
        arguments.variant_id,
        tenant.ingest,
    )
    return PartProposed(part_id=part.record.id, status=part.outcome, facts=part.record.facts)


OPERATIONS: Final = (
    operation(
        name="propose_context_part",
        audience=Audience.AGENT,
        description=PROPOSE_CONTEXT_PART,
        input=ProposeContextPartInput,
        output=PartProposed,
        run=propose_context_part,
    ),
)

from typing import Final

from cad.operations.model import Audience, Input, Tenant, operation
from cad.selections import store
from cad.selections.model import SelectionRecord, parse_selection_id

READ_SELECTION = (
    "What a selection covers: the part of one revision the person pointed at in the 3D view "
    "when they sent a message. The message names the selection's sel- id, and only the person "
    "can make one. Returns the brief_id, slot, revision and variant_id it was made on, and each "
    "picked face (type, area, centre, outward normal, radius and axis of a round face, and the "
    "faces next to it), each picked edge (type, length, centre, direction or radius, and the two "
    "faces it joins), or the whole part with its bounding box. Lengths are in mm, in the "
    "variant's own frame. When a message carries a selection, this, these and it in the message "
    "mean the selection: read variant_code for that variant, find the feature of the code that "
    "makes the picked faces or edges, change that feature, and build the edited code with "
    "build_variant, the brief_id and the slot, so it becomes the slot's next revision. Then score "
    "it with score_variant. A selection is where a change goes, never a load or a check input."
)


class ReadSelectionInput(Input):
    selection_id: str


def read_selection(tenant: Tenant, arguments: ReadSelectionInput) -> SelectionRecord:
    return store.read(tenant.roots.projects, parse_selection_id(arguments.selection_id))


OPERATIONS: Final = (
    operation(
        name="read_selection",
        audience=Audience.AGENT,
        description=READ_SELECTION,
        input=ReadSelectionInput,
        output=SelectionRecord,
        run=read_selection,
    ),
)

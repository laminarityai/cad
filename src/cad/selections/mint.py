"""Resolve what the person picked against the revision's geometry and sign it."""

from cad.operations.model import Tenant
from cad.projects.model import ProjectId
from cad.selections.model import Picked, SelectionNote, SelectionRecord


def mint(tenant: Tenant, project: ProjectId, picked: Picked) -> SelectionRecord:
    """Find the slot and revision of the project that shows `picked.variant_id`, read the
    topology of its BREP, check every picked number is in range, describe each pick, then sign
    and store the record. Raises SelectionRefused with a message the person can read when the
    variant is not in the project, its mesh is not ready, or a number is out of range."""
    raise NotImplementedError


def note(record: SelectionRecord) -> SelectionNote:
    """The transcript's note: the id, and a summary such as "2 faces" or "the whole part"."""
    raise NotImplementedError

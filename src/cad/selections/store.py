"""Signed selections, one file each at <projects>/<project>/selections/<sel-id>.signed, signed
with the project store's key under the slot "<project>/selection/<sel-id>"."""

from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.records import signed
from cad.records.roots import project_store
from cad.selections.model import SelectionId, SelectionRecord, UnknownSelection

DIRECTORY: Final = "selections"


def save(projects: Path, record: SelectionRecord) -> None:
    """Sign and publish the record. A record is written once and never changed."""
    path = projects / record.project_id / DIRECTORY / _file(record.selection_id)
    data = record.model_dump_json().encode()
    slot = _slot(record.project_id, record.selection_id)
    if not signed.publish(project_store(projects), slot, path, data):
        raise FileExistsError(f"selection {record.selection_id} is already stored")


def read(projects: Path, selection_id: SelectionId) -> SelectionRecord:
    """The record, found in whichever project of this account holds it. Raises
    UnknownSelection when none does, or when its signature fails."""
    for path in sorted(projects.glob(f"*/{DIRECTORY}/{_file(selection_id)}")):
        project = path.parent.parent.name
        data = signed.read(project_store(projects), _slot(project, selection_id), path)
        if data is None:
            continue
        try:
            record = SelectionRecord.model_validate_json(data)
        except ValidationError:
            continue
        if record.project_id == project and record.selection_id == selection_id:
            return record
    raise UnknownSelection(
        f"no selection {selection_id} is stored. Only a message from the person carries one; "
        "use the sel- id that message names."
    )


def _file(selection_id: str) -> str:
    return f"{selection_id}.signed"


def _slot(project: str, selection_id: str) -> str:
    return f"{project}/selection/{selection_id}"

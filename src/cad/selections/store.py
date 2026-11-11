"""Signed selections, one file each at <projects>/<project>/selections/<sel-id>.signed, signed
with the project store's key under the slot "<project>/selection/<sel-id>"."""

from pathlib import Path

from cad.selections.model import SelectionId, SelectionRecord


def save(projects: Path, record: SelectionRecord) -> None:
    """Sign and publish the record. A record is written once and never changed."""
    raise NotImplementedError


def read(projects: Path, selection_id: SelectionId) -> SelectionRecord:
    """The record, found in whichever project of this account holds it. Raises
    UnknownSelection when none does, or when its signature fails."""
    raise NotImplementedError

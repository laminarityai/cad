from datetime import date
from pathlib import Path

from cad.projects.model import new_project_id
from cad.research.ledger import (
    Ledger,
    ResearchedRecord,
    Stored,
    Turned,
    append_record,
    read_ledger,
)


def test_a_refused_first_append_leaves_the_research_readable_and_the_next_one_lands(
    tmp_path: Path,
) -> None:
    projects, project = tmp_path / "projects", new_project_id()
    record = ResearchedRecord(
        project=project,
        key="bambu-pla-basic",
        field="yield_strength",
        magnitude=90e6,
        unit="Pa",
        url="https://example.org/pla",
        title="PLA data",
        quote="Yield strength 90 MPa",
        retrieved=date(2026, 11, 13),
        sha256="ab" * 32,
    )
    refused = Turned("yield_strength 90 MPa is above tensile_strength")
    assert append_record(projects, project, record, lambda _held: refused) == refused
    assert read_ledger(projects, project) == Ledger(())
    assert append_record(projects, project, record, lambda _held: None) == Stored(1)
    assert read_ledger(projects, project) == Ledger((record,))

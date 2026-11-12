"""What the agent sees of the files a person added, and how a requirement quotes one (ADR-0012)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.context_parts.store import fit_targets
from cad.projects.model import ProjectId
from cad.research.fetch import FetchFailed, PdfFile, PdfText
from cad.uploads import store, text
from cad.uploads.model import kind_of
from tests.support.rows import RAIL, fake_ingest

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio
TEXT = "A clip that holds the motor"
SPEC = b"# Motor\n\nThe shaft is 5 mm\nacross and 24 mm long.\n"
PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")
SHEET = b"%PDF-1.7 a datasheet"
SCAN = b"%PDF-1.7 a scan"


def reader(pdf: PdfFile) -> PdfText | FetchFailed:
    """The reader image's answer: text for the datasheet, none for the scan."""
    if pdf.body == SCAN:
        return FetchFailed("a PDF with no text layer")
    return PdfText(pdf.url, "Datasheet", ("Shaft", "24 mm long, hardened"), pdf.sha256)


@pytest.fixture(autouse=True)
def reads_pdfs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(text, "read_pdf", reader)


async def project(s: Session) -> dict[str, Any]:
    return await s.call("create_brief", text=TEXT)


def added(s: Session, project_id: str, name: str, data: bytes) -> str:
    projects, at = s.roots.projects, ProjectId(project_id)
    kind = kind_of(name)
    if kind.cad is not None:
        part = store.add_part(projects, at, name, kind, None, data, PERSON, fake_ingest)
        return part.record.id
    return store.add_document(projects, at, name, kind, data, PERSON).id


async def test_list_files_shows_each_supplied_part_with_its_facts_and_each_document(
    s: Session,
) -> None:
    created = await project(s)
    part = added(s, created["project_id"], "motor.step", RAIL)
    spec = added(s, created["project_id"], "spec.md", SPEC)
    listed = await s.call("list_files", project_id=created["project_id"])
    [shown] = listed["parts"]
    assert (shown["part"]["part_id"], shown["part"]["outcome"]) == (part, "confirmed")
    assert shown["facts"]["solids"] == 1
    assert [one["file_id"] for one in listed["documents"]] == [spec]


async def test_read_file_returns_text_and_hands_a_pdf_to_the_chat(s: Session) -> None:
    created = await project(s)
    spec = added(s, created["project_id"], "spec.md", SPEC)
    sheet = added(s, created["project_id"], "sheet.pdf", SHEET)
    text = await s.call("read_file", project_id=created["project_id"], file_id=spec)
    pdf = await s.call("read_file", project_id=created["project_id"], file_id=sheet)
    assert (text["text"], text["attachments"]) == (SPEC.decode(), [])
    assert (pdf["text"], pdf["attachments"]) == (None, [sheet])


async def test_a_requirement_quotes_a_document_and_the_page_names_it(s: Session) -> None:
    created = await project(s)
    spec = added(s, created["project_id"], "spec.md", SPEC)
    sheet = added(s, created["project_id"], "sheet.pdf", SHEET)
    scan = added(s, created["project_id"], "scan.pdf", SCAN)
    shaft = {"kind": "unchecked", "statement": "clears a 5 mm shaft"}
    reach = {"kind": "unchecked", "statement": "reaches 24 mm along the shaft"}
    hard = {"kind": "unchecked", "statement": "the shaft is hardened"}
    proposed = await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[
            {"target": shaft, "quote": "The shaft is 5 mm across", "file_id": spec},
            {"target": reach, "quote": "24 mm long", "file_id": sheet},
            {"target": hard, "quote": "hardened steel", "file_id": scan},
        ],
    )
    origins = [row["requirement"]["origin"] for row in proposed["requirements"]]
    assert [(one["name"], one["checked"]) for one in origins] == [
        ("spec.md", True),
        ("sheet.pdf", True),
        ("scan.pdf", False),
    ]
    await s.call("ask_to_confirm", project_id=created["project_id"])
    _, page = s.person.get(s.person.url)
    assert "From spec.md:" in page
    assert "From sheet.pdf:" in page
    assert "From scan.pdf, as the agent read it:" in page


@pytest.mark.parametrize(
    ("name", "data", "quote"),
    [("spec.md", SPEC, "The shaft is 6 mm across"), ("sheet.pdf", SHEET, "26 mm long")],
)
async def test_a_quote_the_document_does_not_hold_is_refused(
    s: Session, name: str, data: bytes, quote: str
) -> None:
    created = await project(s)
    file_id = added(s, created["project_id"], name, data)
    said = await s.text(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[
            {
                "target": {"kind": "unchecked", "statement": "clears a 6 mm shaft"},
                "quote": quote,
                "file_id": file_id,
            }
        ],
    )
    assert f"requirements[0]: the quote does not appear in {name}" in said


async def test_a_supplied_part_is_a_fit_target_only_when_a_requirement_names_it(
    s: Session,
) -> None:
    created = await project(s)
    part = added(s, created["project_id"], "motor.step", RAIL)
    at, brief = ProjectId(created["project_id"]), created["brief_id"]
    unnamed = fit_targets(s.roots.projects, at, brief, frozenset())
    named = fit_targets(s.roots.projects, at, brief, frozenset({part}))
    assert unnamed == ()
    assert [one.record.id for one in named] == [part]

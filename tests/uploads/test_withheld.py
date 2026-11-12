"""A PDF the person marks as a licensed standard is stored and quotable, and never read by the
agent (ADR-0012). Its text is taken once and stored beside it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.projects.model import ProjectId
from cad.research.fetch import FetchFailed, PdfFile, PdfText
from cad.uploads import store, text
from cad.uploads.model import BadUpload, kind_of

if TYPE_CHECKING:
    from tests.support.session import Session

pytestmark = pytest.mark.anyio
PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")
STANDARD = b"%PDF-1.7 a licensed standard"
SHEET = b"%PDF-1.7 a datasheet"
BRIEF = "A bracket whose walls are at least 3.0 mm thick"
RULE = {"kind": "unchecked", "statement": "walls at least 3.0 mm"}


class Reader:
    """The reader image's answer, and how many times it was asked."""

    def __init__(self) -> None:
        self.asked = 0

    def __call__(self, pdf: PdfFile) -> PdfText | FetchFailed:
        self.asked += 1
        return PdfText(
            pdf.url,
            "Standard",
            ("Scope", "Walls are at least 3.0 mm thick", "Secret clause 9"),
            pdf.sha256,
        )


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> Reader:
    read = Reader()
    monkeypatch.setattr(text, "read_pdf", read)
    return read


def add(s: Session, project: str, name: str, data: bytes, *, withheld: bool = False) -> str:
    kind = kind_of(name)
    found = store.add_document(
        s.roots.projects, ProjectId(project), name, kind, data, PERSON, withheld
    )
    return found.id


async def test_list_files_names_a_withheld_file_and_read_file_refuses_it(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text=BRIEF)
    standard = add(s, created["project_id"], "din.pdf", STANDARD, withheld=True)
    sheet = add(s, created["project_id"], "sheet.pdf", SHEET)
    listed = await s.call("list_files", project_id=created["project_id"])
    assert [(one["name"], one["withheld"]) for one in listed["documents"]] == [
        ("din.pdf", True),
        ("sheet.pdf", False),
    ]
    refused = await s.text("read_file", project_id=created["project_id"], file_id=standard)
    assert "kept from you" in refused
    read = await s.call("read_file", project_id=created["project_id"], file_id=sheet)
    assert read["attachments"] == [sheet]
    assert reader.asked == 0


async def test_a_requirement_quotes_a_withheld_file_with_the_words_the_person_typed(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text=BRIEF)
    standard = add(s, created["project_id"], "din.pdf", STANDARD, withheld=True)
    proposed = await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[
            {"target": RULE, "quote": "at least 3.0 mm thick", "file_id": standard},
        ],
    )
    [origin] = [row["requirement"]["origin"] for row in proposed["requirements"]]
    assert (origin["name"], origin["checked"]) == ("din.pdf", True)
    assert reader.asked == 1


async def test_a_quote_the_person_did_not_type_is_refused_before_the_file_is_looked_at(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text=BRIEF)
    standard = add(s, created["project_id"], "din.pdf", STANDARD, withheld=True)
    refused = [
        await s.text(
            "propose_requirements",
            brief_id=created["brief_id"],
            requirements=[{"target": RULE, "quote": quote, "file_id": standard}],
        )
        for quote in ("Secret clause 9", "a clause that is not in the file")
    ]
    assert all("kept from you" in one and "words they typed" in one for one in refused)
    assert refused[0] == refused[1]
    assert reader.asked == 0


async def test_words_the_person_typed_that_the_file_lacks_are_refused_by_name(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text=BRIEF)
    standard = add(s, created["project_id"], "din.pdf", STANDARD, withheld=True)
    said = await s.text(
        "propose_requirements",
        brief_id=created["brief_id"],
        said="and the standard says thicker than 4 mm",
        requirements=[{"target": RULE, "quote": "thicker than 4 mm", "file_id": standard}],
    )
    assert "the quote does not appear in din.pdf" in said


async def test_a_later_message_of_the_person_is_added_to_the_brief_with_a_withheld_quote(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text="A bracket")
    standard = add(s, created["project_id"], "din.pdf", STANDARD, withheld=True)
    await s.call(
        "propose_requirements",
        brief_id=created["brief_id"],
        said="DIN says walls are at least 3.0 mm thick",
        requirements=[
            {"target": RULE, "quote": "at least 3.0 mm thick", "file_id": standard},
        ],
    )
    shown: dict[str, Any] = await s.call("list_requirements", brief_id=created["brief_id"])
    assert "DIN says walls are at least 3.0 mm thick" in shown["text"]


async def test_a_withheld_file_without_text_cannot_be_quoted(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:

    def scan(pdf: PdfFile) -> PdfText | FetchFailed:
        return FetchFailed("no text layer")

    monkeypatch.setattr(text, "read_pdf", scan)
    created = await s.call("create_brief", text=BRIEF)
    scan = add(s, created["project_id"], "scan.pdf", STANDARD, withheld=True)
    said = await s.text(
        "propose_requirements",
        brief_id=created["brief_id"],
        requirements=[{"target": RULE, "quote": "at least 3.0 mm thick", "file_id": scan}],
    )
    assert "holds no text the server can read" in said


async def test_the_text_is_read_once_and_a_file_without_it_gets_it_on_first_need(
    s: Session, reader: Reader
) -> None:
    created = await s.call("create_brief", text=BRIEF)
    project = created["project_id"]
    sheet = add(s, project, "sheet.pdf", SHEET)
    sources = s.roots.projects / project / store.SOURCES
    assert not list(sources.glob(f"*{text.SUFFIX}"))
    quote = {"target": RULE, "quote": "at least 3.0 mm thick", "file_id": sheet}
    for _ in range(3):
        await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[quote])
    assert reader.asked == 1
    [stored] = sources.glob(f"*{text.SUFFIX}")
    assert "Walls are at least 3.0 mm thick" in stored.read_text()
    stored.unlink()
    await s.call("propose_requirements", brief_id=created["brief_id"], requirements=[quote])
    assert reader.asked == 2


def test_adding_the_same_pdf_again_with_the_other_choice_changes_it(
    tmp_path: Any,
) -> None:
    project = ProjectId("p" * 16)
    kind = kind_of("din.pdf")
    first = store.add_document(tmp_path, project, "din.pdf", kind, STANDARD, PERSON)
    same = store.add_document(tmp_path, project, "din.pdf", kind, STANDARD, PERSON)
    flipped = store.add_document(tmp_path, project, "din.pdf", kind, STANDARD, PERSON, True)
    again = store.add_document(tmp_path, project, "din.pdf", kind, STANDARD, PERSON, True)
    assert (first.withheld, same.withheld, flipped.withheld, again.withheld) == (
        False,
        False,
        True,
        True,
    )
    assert [one.withheld for one in store.documents(tmp_path, project)] == [True]
    back = store.add_document(tmp_path, project, "din.pdf", kind, STANDARD, PERSON, False)
    assert (back.withheld, [one.withheld for one in store.documents(tmp_path, project)]) == (
        False,
        [False],
    )


def test_only_a_pdf_can_be_withheld(tmp_path: Any) -> None:
    with pytest.raises(BadUpload, match="only a PDF"):
        store.add_document(
            tmp_path, ProjectId("p" * 16), "n.md", kind_of("n.md"), b"# n", PERSON, True
        )

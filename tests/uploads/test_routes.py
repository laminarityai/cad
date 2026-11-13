"""The person adds files to a project from the web app: one raw-bytes POST per file (ADR-0012)."""

from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pytest

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.briefs.store import create_brief
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.model import FromUpload, StlRead
from cad.context_parts.store import confirmed_parts, newest_parts
from cad.operations.tenants import Tenants
from cad.projects.model import ProjectId, new_project_id
from cad.research.fetch import FetchFailed, PdfFile, PdfText
from cad.sandbox.outcome import SandboxUnavailable
from cad.server.hosted import build_app
from cad.uploads import text
from tests.support.browser import Person, local_pages
from tests.support.chat import ALICE, BOB, JSON, Chat, script, step
from tests.support.hosted import BASE
from tests.support.rows import NOT_A_PART, RAIL, fake_ingest

pytestmark = pytest.mark.anyio
OCTETS = {"Content-Type": "application/octet-stream"}


@pytest.fixture
async def chat(tmp_path: Path, person: Person) -> AsyncIterator[Chat]:
    local = LocalIssuer.open(tmp_path, BASE)
    door = Door(open_page=local_pages(person, lambda account: tenants.of(account)), wait_seconds=5)
    tenants = Tenants(tmp_path / "accounts", 600, door, fake_ingest)
    app = build_app(local.issuer(), tenants, LocalSignIn(local), script(step("Hello.")))
    async with app.router.lifespan_context(app):
        yield Chat(app, local, tenants)


def project_of(chat: Chat) -> ProjectId:
    roots = chat.tenants.of(AccountId(ALICE)).roots
    return create_brief(roots, "A clip that holds the motor", new_project_id()).project


async def add(
    client: httpx2.AsyncClient, project: str, name: str, data: bytes, **query: str
) -> httpx2.Response:
    return await client.post(
        f"/v1/projects/{project}/files",
        params={"name": name, **query},
        headers=OCTETS,
        content=data,
    )


async def test_an_uploaded_step_is_a_confirmed_part_the_fit_check_reads(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        added = await add(client, project, "motor.step", RAIL)
        shown = await client.get(f"/v1/projects/{project}")
    assert added.status_code == 200, added.text
    part = added.json()["part"]
    assert (part["origin"], part["outcome"], part["name"]) == ("upload", "confirmed", "motor")
    assert [one["part_id"] for one in shown.json()["context_parts"]] == [part["part_id"]]
    projects = chat.tenants.of(AccountId(ALICE)).roots.projects
    assert [one.record.id for one in confirmed_parts(projects, project)] == [part["part_id"]]


async def test_the_same_file_again_is_the_same_part(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        first = await add(client, project, "motor.step", RAIL)
        again = await add(client, project, "motor-copy.stp", RAIL)
    assert again.json()["part"]["part_id"] == first.json()["part"]["part_id"]


async def test_an_stl_needs_the_persons_unit(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        unitless = await add(client, project, "bracket.stl", RAIL)
        inches = await add(client, project, "bracket.stl", RAIL, unit="in")
    assert unitless.status_code == 400
    assert "holds no units" in unitless.json()["error"]
    assert inches.status_code == 200, inches.text
    projects = chat.tenants.of(AccountId(ALICE)).roots.projects
    [stored] = newest_parts(projects, project)
    assert isinstance(stored.record.source, FromUpload)
    assert stored.record.source.read_as == StlRead(unit="in")


async def test_a_declined_part_leaves_the_fit_check_until_it_is_sent_again(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        part = (await add(client, project, "motor.step", RAIL)).json()["part"]["part_id"]
        declined = await client.post(
            f"/v1/projects/{project}/parts/{part}/decline", headers=JSON, content=b"{}"
        )
        again = await client.post(
            f"/v1/projects/{project}/parts/{part}/decline", headers=JSON, content=b"{}"
        )
        shown = await client.get(f"/v1/projects/{project}")
        left = confirmed_parts(chat.tenants.of(AccountId(ALICE)).roots.projects, project)
        await add(client, project, "motor.step", RAIL)
        sent_again = await client.get(f"/v1/projects/{project}")
    assert declined.json() == {"part_id": part, "declined": True}
    assert again.json() == {"part_id": part, "declined": False}
    assert shown.json()["context_parts"][0]["outcome"] == "declined"
    assert left == ()
    assert [one["outcome"] for one in sent_again.json()["context_parts"]] == ["confirmed"]


async def test_a_document_is_a_source_of_the_project(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        added = await add(client, project, "spec.md", b"# Motor\nNEMA 17, 42 mm square\n")
        shown = await client.get(f"/v1/projects/{project}")
    assert added.json()["kind"] == "document"
    assert [one["name"] for one in shown.json()["documents"]] == ["spec.md"]


@pytest.mark.parametrize(
    ("name", "data", "headers", "status"),
    [
        ("motor.step", RAIL, JSON, 415),
        ("motor.exe", RAIL, OCTETS, 400),
        ("../motor.step", RAIL, OCTETS, 422),
        ("empty.step", NOT_A_PART, OCTETS, 400),
        ("notes.txt", b"\xff\xfe", OCTETS, 400),
    ],
)
async def test_a_file_the_project_cannot_take_is_refused(
    chat: Chat, name: str, data: bytes, headers: dict[str, str], status: int
) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        sent = await client.post(
            f"/v1/projects/{project}/files", params={"name": name}, headers=headers, content=data
        )
        shown = await client.get(f"/v1/projects/{project}")
    assert sent.status_code == status, sent.text
    assert shown.json()["context_parts"] == shown.json()["documents"] == []


async def test_only_the_projects_own_person_adds_to_it(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client(None) as nobody, chat.client(BOB) as bob:
        signed_out = await add(nobody, project, "motor.step", RAIL)
        other = await add(bob, project, "motor.step", RAIL)
    assert signed_out.status_code == 401
    assert other.status_code == 404


STANDARD = b"%PDF-1.7 a licensed standard"


async def test_a_pdf_marked_as_a_standard_is_withheld_and_its_text_is_stored_at_upload(
    chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def reader(pdf: PdfFile) -> PdfText | FetchFailed:
        asked.append(pdf.url)
        return PdfText(pdf.url, "Standard", ("Walls are 3 mm",), pdf.sha256)

    monkeypatch.setattr(text, "read_pdf", reader)
    project = project_of(chat)
    async with chat.client() as client:
        added = await add(client, project, "din.pdf", STANDARD, withheld="true")
        plain = await add(client, project, "sheet.pdf", b"%PDF-1.7 other")
        shown = await client.get(f"/v1/projects/{project}")
    assert added.json()["document"]["withheld"] is True
    assert plain.json()["document"]["withheld"] is False
    assert [(one["name"], one["withheld"]) for one in shown.json()["documents"]] == [
        ("din.pdf", True),
        ("sheet.pdf", False),
    ]
    assert asked == ["din.pdf", "sheet.pdf"]


async def test_an_upload_still_works_when_the_reader_cannot_run(
    chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(pdf: PdfFile) -> PdfText | FetchFailed:
        raise SandboxUnavailable("Docker is not running")

    monkeypatch.setattr(text, "read_pdf", down)
    project = project_of(chat)
    async with chat.client() as client:
        added = await add(client, project, "din.pdf", STANDARD, withheld="true")
    assert added.status_code == 200, added.text


async def test_only_a_pdf_is_marked_as_a_standard(chat: Chat) -> None:
    project = project_of(chat)
    async with chat.client() as client:
        refused = await add(client, project, "spec.md", b"# Motor\n", withheld="true")
    assert refused.status_code == 400
    assert "only a PDF" in refused.json()["error"]

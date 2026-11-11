import json
import shutil

import pytest
from mcp import Client
from mcp.server import MCPServer

from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tools import tools
from cad.projects.model import ProjectId
from cad.selections import mint, store
from cad.selections.model import (
    Picked,
    SelectionRecord,
    SelectionRefused,
    UnknownSelection,
    parse_selection_id,
)
from tests.selections.support import TOP, Project, confirmed, failed, joined, stored_mesh

pytestmark = pytest.mark.anyio

FIRST, SECOND = "result = 1\n", "result = 2\n"


def pick(variant: str, **kinds: object) -> Picked:
    return Picked.model_validate({"variant_id": variant, **kinds})


def minted(tenant: Tenant, project: ProjectId, picked: Picked) -> SelectionRecord:
    return mint.mint(
        tenant.roots, project, picked, variants=tenant.variants, geometry=tenant.geometry
    )


@pytest.fixture
async def design(alice: Tenant) -> tuple[Project, str]:
    project = await confirmed(alice)
    stored_mesh(alice)
    return project, joined(alice, project.brief, FIRST)


async def test_a_picked_face_is_described_where_it_sits_in_its_slot(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, faces=[TOP]))
    assert (record.project_id, record.brief_id, record.slot, record.revision) == (
        project.project,
        project.brief,
        1,
        1,
    )
    assert record.variant_id == vid
    [face] = record.faces
    assert (face.face, face.type, face.normal) == (TOP, "PLANE", (0.0, 0.0, 1.0))
    assert [one.face for one in face.adjacent] == [0, 1, 2, 3]
    assert mint.note(record).summary == "1 face"


async def test_faces_and_an_edge_are_summarised_and_an_edge_names_the_faces_it_joins(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, faces=[0, 1], edges=[3]))
    assert mint.note(record).summary == "2 faces and 1 edge"
    [edge] = record.edges
    assert [one.face for one in edge.between] == [0, 5]


async def test_the_whole_part_is_its_counts_and_bounding_box(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, part=True))
    assert record.part is not None
    assert (record.part.faces, record.part.edges) == (6, 12)
    assert record.part.bounding_box.min_mm == (-5.0, -10.0, 0.0)
    assert record.part.bounding_box.max_mm == (5.0, 10.0, 6.0)
    assert mint.note(record).summary == "the whole part"


async def test_an_earlier_revision_is_named_by_its_own_number(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, first = design
    second = joined(alice, project.brief, SECOND, slot=1)
    project_id = ProjectId(project.project)
    assert minted(alice, project_id, pick(first, part=True)).revision == 1
    assert minted(alice, project_id, pick(second, part=True)).revision == 2


async def test_a_variant_of_another_project_is_refused(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, _ = design
    other = await confirmed(alice)
    foreign = joined(alice, other.brief, SECOND)
    with pytest.raises(SelectionRefused, match="not a design of this project"):
        minted(alice, ProjectId(project.project), pick(foreign, part=True))
    with pytest.raises(SelectionRefused, match="not a design of this project"):
        minted(alice, ProjectId(project.project), pick("0" * 16, part=True))


@pytest.mark.parametrize(("kind", "held"), [("faces", 6), ("edges", 12)])
async def test_a_number_beyond_the_geometry_is_refused_and_nothing_is_signed(
    alice: Tenant, design: tuple[Project, str], kind: str, held: int
) -> None:
    project, vid = design
    with pytest.raises(SelectionRefused, match=f"has {held} {kind[:-1]}s"):
        minted(alice, ProjectId(project.project), pick(vid, **{kind: [held]}))
    assert not (alice.roots.projects / project.project / store.DIRECTORY).exists()


async def test_a_mesh_that_failed_cannot_be_picked_from(alice: Tenant) -> None:
    project = await confirmed(alice)
    stored_mesh(alice, failed())
    vid = joined(alice, project.brief, FIRST)
    with pytest.raises(SelectionRefused, match="a bad BREP"):
        minted(alice, ProjectId(project.project), pick(vid, part=True))


async def test_a_signed_record_reads_back_and_a_broken_signature_reads_as_unknown(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, faces=[TOP]))
    sel = parse_selection_id(record.selection_id)
    assert store.read(alice.roots.projects, sel) == record
    path = alice.roots.projects / project.project / store.DIRECTORY / f"{sel}.signed"
    data = bytearray(path.read_bytes())
    data[0] = ord("0") if data[0] != ord("0") else ord("1")
    path.write_bytes(bytes(data))
    with pytest.raises(UnknownSelection):
        store.read(alice.roots.projects, sel)


async def test_a_record_copied_into_another_project_is_not_valid_there(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, faces=[TOP]))
    sel = parse_selection_id(record.selection_id)
    source = alice.roots.projects / project.project / store.DIRECTORY / f"{sel}.signed"
    moved = alice.roots.projects / "p-0123456789abcdef" / store.DIRECTORY
    moved.mkdir(parents=True)
    shutil.copy(source, moved / source.name)
    source.unlink()
    with pytest.raises(UnknownSelection):
        store.read(alice.roots.projects, sel)


async def test_the_agent_reads_a_selection_by_its_id_and_cannot_make_one(
    alice: Tenant, design: tuple[Project, str]
) -> None:
    project, vid = design
    record = minted(alice, ProjectId(project.project), pick(vid, faces=[TOP]))
    server = MCPServer("cad", tools=tools(lambda: alice, OPERATIONS))
    async with Client(server) as client:
        listed = {one.name for one in (await client.list_tools()).tools}
        read = await client.call_tool("read_selection", {"selection_id": record.selection_id})
        missing = await client.call_tool("read_selection", {"selection_id": "sel-" + "0" * 16})
    assert "read_selection" in listed
    assert {"make_selection", "select"}.isdisjoint(listed)
    assert not read.is_error
    assert read.structured_content is not None
    found = json.loads(json.dumps(read.structured_content))
    assert (found["brief_id"], found["slot"], found["revision"]) == (project.brief, 1, 1)
    assert found["faces"][0]["normal"] == [0.0, 0.0, 1.0]
    assert missing.is_error
    assert "UnknownSelection" in json.dumps([c.model_dump() for c in missing.content])

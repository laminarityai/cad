import hashlib
import json
import threading
from collections.abc import Iterator
from typing import Any, cast

import pytest
from mcp import Client
from mcp.server import MCPServer
from mcp_types import TextContent

from cad.accounts.principal import AccountId
from cad.chat.turn import MAX_RESULT_CHARS
from cad.geometry import job
from cad.geometry.bodies import BodyFaces
from cad.geometry.container.wire import FaceFacts
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Tessellated
from cad.operations import reads
from cad.operations.model import Tenant
from cad.operations.registry import OPERATIONS
from cad.operations.tenants import Tenants
from cad.operations.tools import tools
from cad.operations.variants import BuildVariantInput, build_variant
from cad.sandbox.bodies import Body
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Area, Build, Built, NoResult
from cad.variants import entry

RAIL = b"CASCADE Topology V3, a rail\n"
SHA = hashlib.sha256(RAIL).hexdigest()
MESH = Tessellated.model_validate(
    {
        "brep_sha256": SHA,
        "version": job.VERSION,
        "shapes": {
            "version": 3,
            "id": "/rail",
            "name": "rail",
            "parts": [],
            "loc": ((0, 0, 0), (0, 0, 0, 1)),
            "normal_len": 0,
            "bb": {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1},
        },
        "topology": {"faces": [], "edges": []},
    }
)


class Gated:
    def __init__(self) -> None:
        self.mesh = MESH
        self.calls: list[str] = []
        self.started = threading.Event()
        self.gate = threading.Event()

    def __call__(self, brep: bytes, brep_sha256: str) -> job.Ran:
        assert brep == RAIL
        self.calls.append(brep_sha256)
        self.started.set()
        self.gate.wait(5)
        return job.Ran(self.mesh, True)


@pytest.fixture
def alice(tenants: Tenants) -> Tenant:
    return tenants.of(AccountId("user_alice"))


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> Iterator[Gated]:
    gated = Gated()
    monkeypatch.setattr(TESSELLATIONS, "_run", gated)
    yield gated
    gated.gate.set()


def stored_build(tenant: Tenant, code: str, outcome: Built | NoResult) -> str:
    vid = entry.variant_id(code, image_tag(BUILD))
    brep = RAIL if isinstance(outcome, Built) else None
    entry.save(tenant.variants, vid, code, Build(outcome=outcome, output=""), brep)
    return vid


def test_a_build_starts_its_mesh_so_view_turns_ready_with_no_geometry_read(
    alice: Tenant, run: Gated
) -> None:
    vid = stored_build(alice, "result = 1", Built())
    build_variant(alice, BuildVariantInput(code="result = 1"))
    assert run.started.wait(5)
    pending = reads.view(alice, reads.VariantInput(variant_id=vid))
    assert (pending.mesh, pending.mesh_url) == ("pending", None)
    run.gate.set()
    assert (
        TESSELLATIONS.read(
            alice.geometry, entry.open_entry(alice.variants, vid, image_tag(BUILD)), 5
        )
        == MESH
    )
    ready = reads.view(alice, reads.VariantInput(variant_id=vid))
    assert ready.mesh == "tessellated"
    assert ready.mesh_url == f"/v1/geometry/{job.VERSION}/{SHA}.json"
    assert run.calls == [SHA]


def test_view_starts_the_mesh_it_reports_pending_when_no_job_is_making_it(
    alice: Tenant, run: Gated
) -> None:
    vid = stored_build(alice, "result = 2", Built())
    asked = reads.VariantInput(variant_id=vid)
    assert [reads.view(alice, asked).mesh for _ in range(3)] == ["pending"] * 3
    assert run.started.wait(5)
    assert run.calls == [SHA]


def test_a_build_with_no_shape_starts_no_mesh(alice: Tenant, run: Gated) -> None:
    stored_build(alice, "result = None", NoResult(reason="no shape"))
    build_variant(alice, BuildVariantInput(code="result = None"))
    assert not run.started.wait(0.2)


FACE: FaceFacts = {
    "type": "plane",
    "area": 1.0,
    "center": (0, 0, 0),
    "normal": (0, 0, 1),
    "radius": None,
    "axis": None,
    "edges": [],
}
TWO_FACES = MESH.model_copy(update={"topology": {"faces": [FACE, FACE], "edges": []}})
GRIP = Area(name="grip", colour="#1a1a1a", faces=(1,))


@pytest.mark.parametrize(
    ("areas", "shown"),
    [
        pytest.param((GRIP,), (GRIP,), id="every-face-on-the-mesh"),
        pytest.param((GRIP.model_copy(update={"faces": (1, 2)}),), (), id="a-face-past-the-mesh"),
    ],
)
def test_view_shows_the_areas_only_when_the_mesh_has_every_face_they_name(
    alice: Tenant, run: Gated, areas: tuple[Area, ...], shown: tuple[Area, ...]
) -> None:
    run.mesh = TWO_FACES
    vid = stored_build(alice, f"result = {len(areas[0].faces)}", Built(areas=areas))
    held = entry.open_entry(alice.variants, vid, image_tag(BUILD))
    pending = reads.view(alice, reads.VariantInput(variant_id=vid))
    assert (pending.mesh, pending.areas) == ("pending", ())
    run.gate.set()
    assert TESSELLATIONS.read(alice.geometry, held, 5) == TWO_FACES
    assert reads.view(alice, reads.VariantInput(variant_id=vid)).areas == shown


def test_view_gives_each_body_the_faces_of_its_solids(alice: Tenant, run: Gated) -> None:
    run.mesh = MESH.model_copy(update={"solid_faces": (6, 3, 3)})
    bodies = (Body(name="plate", solids=(0,)), Body(name="gear", solids=(1, 2)))
    vid = stored_build(alice, "result = 4", Built(bodies=bodies))
    held = entry.open_entry(alice.variants, vid, image_tag(BUILD))
    asked = reads.VariantInput(variant_id=vid)
    assert reads.view(alice, asked).bodies == ()
    run.gate.set()
    assert TESSELLATIONS.read(alice.geometry, held, 5) == run.mesh
    assert reads.view(alice, asked).bodies == (
        BodyFaces(name="plate", faces=(0, 1, 2, 3, 4, 5)),
        BodyFaces(name="gear", faces=(6, 7, 8, 9, 10, 11)),
    )


@pytest.mark.anyio
async def test_a_build_tells_the_agent_each_area_by_its_face_count_within_the_chat_limit(
    alice: Tenant, run: Gated
) -> None:
    many = Area(name="body", colour="#a6abb2", faces=tuple(range(10_000)))
    stored_build(alice, "result = 3", Built(areas=(many,)))
    server = MCPServer("cad", tools=tools(lambda: alice, OPERATIONS))
    async with Client(server) as client:
        result = await client.call_tool("build_variant", {"code": "result = 3"})
    told = cast(dict[str, Any], result.structured_content)
    assert told["outcome"]["areas"] == [{"name": "body", "colour": "#a6abb2", "face_count": 10_000}]
    text = "\n".join(one.text for one in result.content if isinstance(one, TextContent))
    assert len(json.dumps(told, separators=(",", ":"))) < MAX_RESULT_CHARS
    assert 0 < len(text) < MAX_RESULT_CHARS

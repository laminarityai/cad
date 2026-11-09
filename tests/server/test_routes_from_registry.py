import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.accounts.tenants import Tenants
from cad.confirmations.ballot import OS_OPEN
from cad.context_parts.ingest import ingest
from cad.geometry import job, store
from cad.geometry.model import TessellationFailed
from cad.operations.model import Audience, Operation
from cad.operations.registry import OPERATIONS, ROUTES
from cad.operations.routes import Served, person_routes
from cad.operations.tools import agent_operations
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.server.hosted import build_app
from cad.variants import entry

pytestmark = pytest.mark.anyio

BASE = "http://127.0.0.1:8765"
RAIL = b"CASCADE Topology V3, a rail\n"
SHA = hashlib.sha256(RAIL).hexdigest()
ALICE, BOB = AccountId("user_alice"), AccountId("user_bob")


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    return Tenants(tmp_path / "accounts", 60, OS_OPEN, 0.3, ingest)


@pytest.fixture
async def app(local: LocalIssuer, tenants: Tenants) -> AsyncIterator[Starlette]:
    app = build_app(local.issuer(), tenants)
    async with app.router.lifespan_context(app):
        yield app


def client(app: Starlette, token: str, scheme: str = "cookie") -> httpx2.AsyncClient:
    transport = httpx2.ASGITransport(app=app)
    if scheme == "bearer":
        return httpx2.AsyncClient(
            transport=transport, base_url=BASE, headers={"Authorization": f"Bearer {token}"}
        )
    return httpx2.AsyncClient(transport=transport, base_url=BASE, cookies={"__session": token})


def web_routes(app: Starlette) -> dict[str, str]:
    return {
        route.name: route.path
        for route in app.router.routes
        if isinstance(route, Route) and route.path.startswith("/v1/")
    }


async def test_every_web_route_comes_from_a_registry_operation(app: Starlette) -> None:
    reachable = {one.name for one in OPERATIONS if Audience.PERSON in one.audience}
    assert web_routes(app) == {name: served.path for name, served in ROUTES.items()}
    assert set(web_routes(app)) == reachable


def test_an_operation_with_no_route_and_a_route_with_no_operation_are_both_refused() -> None:
    person = [one for one in OPERATIONS if Audience.PERSON in one.audience]
    with pytest.raises(ValueError, match="lack a partner"):
        person_routes(person, {}, lambda _: None, lambda _: None)  # pyright: ignore[reportArgumentType]
    stray: dict[str, Served] = {**ROUTES, "stray": Served("/v1/stray")}
    with pytest.raises(ValueError, match="stray"):
        person_routes(person, stray, lambda _: None, lambda _: None)  # pyright: ignore[reportArgumentType]


def test_no_person_only_operation_is_an_agent_tool() -> None:
    only_person: list[Operation] = [one for one in OPERATIONS if one.audience == Audience.PERSON]
    assert only_person
    assert not set(only_person) & set(agent_operations(OPERATIONS))


@pytest.mark.parametrize(
    "path",
    [
        "/v1/projects",
        "/v1/projects/p-0123456789abcdef",
        "/v1/briefs/0123456789abcdef",
        "/v1/projects/p-0123456789abcdef/briefs/0123456789abcdef/set",
        "/v1/variants/0123456789abcdef",
        "/v1/variants/0123456789abcdef/geometry",
        "/v1/geometry/" + SHA + ".json",
        "/v1/server",
        "/v1/materials",
    ],
)
async def test_an_agent_token_is_refused_on_every_web_route(
    app: Starlette, local: LocalIssuer, path: str
) -> None:
    async with client(app, local.mint_agent("user_alice"), "bearer") as http:
        refused = await http.get(path)
    assert refused.status_code == 401
    assert "sign in" in refused.json()["error"]


async def test_a_person_lists_their_projects_and_no_one_elses(
    app: Starlette, local: LocalIssuer
) -> None:
    async with client(app, local.mint_person("user_alice")) as http:
        listed = await http.get("/v1/projects")
    assert listed.status_code == 200
    assert listed.json() == {"projects": []}


async def test_another_accounts_ids_are_not_found(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    code = "result = None"
    vid = entry.variant_id(code, image_tag(BUILD))
    alice = tenants.of(ALICE)
    entry.save(alice.variants, vid, code, Build(outcome=Built(), output=""), RAIL)
    stored = TessellationFailed(brep_sha256=SHA, version=job.VERSION, reason="x")
    store.write(alice.geometry, stored)
    paths = [f"/v1/variants/{vid}", f"/v1/geometry/{SHA}.json"]
    async with client(app, local.mint_person("user_alice")) as mine:
        reached = [(await mine.get(path)).status_code for path in paths]
    async with client(app, local.mint_person("user_bob")) as theirs:
        refused = [await theirs.get(path) for path in paths]
    assert reached == [200, 200]
    assert [one.status_code for one in refused] == [404, 404]
    assert all(set(one.json()) == {"error"} for one in refused)


async def test_a_mesh_is_immutable_and_a_matching_etag_gets_304(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    store.write(
        tenants.of(ALICE).geometry,
        TessellationFailed(brep_sha256=SHA, version=job.VERSION, reason="x"),
    )
    path = f"/v1/geometry/{SHA}.json"
    async with client(app, local.mint_person("user_alice")) as http:
        first = await http.get(path)
        again = await http.get(path, headers={"If-None-Match": first.headers["ETag"]})
        other = await http.get(path, headers={"If-None-Match": '"nope"'})
    assert first.status_code == 200
    assert "immutable" in first.headers["Cache-Control"]
    assert (again.status_code, again.content) == (304, b"")
    assert again.headers["ETag"] == first.headers["ETag"]
    assert other.status_code == 200


async def test_a_mesh_not_stored_is_404(app: Starlette, local: LocalIssuer) -> None:
    async with client(app, local.mint_person("user_alice")) as http:
        missing = await http.get(f"/v1/geometry/{SHA}.json")
        malformed = await http.get("/v1/geometry/not-a-hash.json")
    assert missing.status_code == 404
    assert malformed.status_code == 422

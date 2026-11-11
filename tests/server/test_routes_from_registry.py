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
from cad.chat.routes import CHAT_ROUTES
from cad.confirmations.waiting import Door
from cad.confirmations.web import CARD_PATH, LocalSignIn
from cad.context_parts.ingest import ingest
from cad.geometry import job, store
from cad.geometry.model import Tessellated, TessellationFailed
from cad.operations.events import EVENTS_PATH
from cad.operations.model import Audience, Operation, Tenant
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
OUTSIDE_REGISTRY = CHAT_ROUTES | {("scorecard_events", EVENTS_PATH), ("confirmation", CARD_PATH)}


def tessellated(name: str) -> Tessellated:
    box = {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1}
    return Tessellated.model_validate(
        {
            "brep_sha256": SHA,
            "version": job.VERSION,
            "shapes": {
                "version": 3,
                "id": "/" + name,
                "name": name,
                "parts": [],
                "loc": [[0, 0, 0], [0, 0, 0, 1]],
                "normal_len": 0,
                "bb": box,
            },
            "topology": {"faces": [], "edges": []},
        }
    )


def mesh_path() -> str:
    return f"/v1/geometry/{job.VERSION}/{SHA}.json"


@pytest.fixture
def local(tmp_path: Path) -> LocalIssuer:
    return LocalIssuer.open(tmp_path, BASE)


@pytest.fixture
def tenants(tmp_path: Path) -> Tenants:
    return Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest)


@pytest.fixture
async def app(local: LocalIssuer, tenants: Tenants) -> AsyncIterator[Starlette]:
    app = build_app(local.issuer(), tenants, LocalSignIn(local))
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
        if isinstance(route, Route)
        and route.path.startswith("/v1/")
        and (route.name, route.path) not in OUTSIDE_REGISTRY
    }


@pytest.mark.parametrize("name", sorted(name for name, _ in OUTSIDE_REGISTRY))
async def test_a_stray_route_named_like_an_exempt_route_is_not_exempt(
    app: Starlette, name: str
) -> None:
    app.router.routes.append(Route("/v1/stray", endpoint=Starlette(), name=name))
    assert web_routes(app)[name] == "/v1/stray"


async def test_every_exempt_route_is_served(app: Starlette) -> None:
    served = {(r.name, r.path) for r in app.router.routes if isinstance(r, Route)}
    assert served >= OUTSIDE_REGISTRY


async def test_every_web_route_comes_from_a_registry_operation(app: Starlette) -> None:
    reachable = {one.name for one in OPERATIONS if Audience.PERSON in one.audience}
    assert web_routes(app) == {name: served.path for name, served in ROUTES.items()}
    assert set(web_routes(app)) == reachable


def no_tenant(account: AccountId) -> Tenant:
    raise AssertionError(f"no request should reach {account}")


def test_an_operation_with_no_route_and_a_route_with_no_operation_are_both_refused() -> None:
    person = [one for one in OPERATIONS if Audience.PERSON in one.audience]
    with pytest.raises(ValueError, match="lack a partner"):
        person_routes(person, {}, lambda _: None, no_tenant)
    stray: dict[str, Served] = {**ROUTES, "stray": Served("/v1/stray")}
    with pytest.raises(ValueError, match="stray"):
        person_routes(person, stray, lambda _: None, no_tenant)


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
        "/v1/variants/0123456789abcdef/events",
        f"/v1/geometry/{job.VERSION}/{SHA}.json",
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
    store.write(alice.geometry, tessellated("rail"))
    paths = [f"/v1/variants/{vid}", mesh_path()]
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
    store.write(tenants.of(ALICE).geometry, tessellated("rail"))
    async with client(app, local.mint_person("user_alice")) as http:
        first = await http.get(mesh_path())
        etag = first.headers["ETag"]
        asked = [etag, f"W/{etag}", "*", f'"nope", {etag}', '"nope"']
        again = [await http.get(mesh_path(), headers={"If-None-Match": tag}) for tag in asked]
    assert first.status_code == 200
    assert "immutable" in first.headers["Cache-Control"]
    assert [one.status_code for one in again] == [304, 304, 304, 304, 200]
    assert {(one.content, one.headers["ETag"]) for one in again[:4]} == {(b"", etag)}


async def test_a_mesh_not_stored_or_failed_is_404_and_never_immutable(
    app: Starlette, local: LocalIssuer, tenants: Tenants
) -> None:
    async with client(app, local.mint_person("user_alice")) as http:
        missing = await http.get(mesh_path())
        store.write(
            tenants.of(ALICE).geometry,
            TessellationFailed(brep_sha256=SHA, version=job.VERSION, reason="x"),
        )
        failed = await http.get(mesh_path())
        malformed = await http.get(f"/v1/geometry/{job.VERSION}/not-a-hash.json")
    assert [missing.status_code, failed.status_code] == [404, 404]
    assert all("Cache-Control" not in one.headers for one in (missing, failed))
    assert malformed.status_code == 422


async def test_a_new_tessellator_version_moves_the_mesh_to_a_new_url(
    app: Starlette, local: LocalIssuer, tenants: Tenants, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = "result = None"
    vid = entry.variant_id(code, image_tag(BUILD))
    alice = tenants.of(ALICE)
    entry.save(alice.variants, vid, code, Build(outcome=Built(), output=""), RAIL)
    store.write(alice.geometry, tessellated("old"))
    async with client(app, local.mint_person("user_alice")) as http:
        old_url = (await http.get(f"/v1/variants/{vid}")).json()["mesh_url"]
        old = await http.get(old_url)
        monkeypatch.setattr(job, "VERSION", "b" * 12)
        stale = await http.get(old_url)
        pending = (await http.get(f"/v1/variants/{vid}")).json()
        store.write(alice.geometry, tessellated("new"))
        new_url = (await http.get(f"/v1/variants/{vid}")).json()["mesh_url"]
        new = await http.get(new_url)
        stale_after = await http.get(old_url)
    assert old_url == f"/v1/geometry/{old.json()['version']}/{SHA}.json"
    assert (pending["mesh"], pending["mesh_url"]) == ("pending", None)
    assert new_url == f"/v1/geometry/{'b' * 12}/{SHA}.json" != old_url
    assert [old.status_code, new.status_code] == [200, 200]
    assert new.json()["shapes"]["name"] == "new" != old.json()["shapes"]["name"]
    assert [stale.status_code, stale_after.status_code] == [404, 404]
    assert all("Cache-Control" not in one.headers for one in (stale, stale_after))

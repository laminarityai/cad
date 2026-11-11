import asyncio
import json
import threading
from collections.abc import AsyncGenerator, Callable, MutableMapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId, PersonSession
from cad.checks.jobs import JobSpec, Quick
from cad.checks.lanes import Listener
from cad.checks.report import SPECS, build_request
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations import events
from cad.operations.events import events_route
from cad.operations.model import Tenant
from cad.operations.scorecards import ScorecardInput
from cad.operations.tenants import Tenants
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.scorecard.material import ScorecardSnapshot, snapshot
from cad.scorecard.score import NotScored
from cad.server.hosted import build_app
from cad.tables.materials import load_materials
from cad.variants import entry
from cad.variants.entry import UnknownVariant
from tests.support.hosted import BASE
from tests.support.scorecard import reported

pytestmark = pytest.mark.anyio

ALICE = AccountId("user_alice")
VID = "0123456789abcdef"
PATH = f"/v1/variants/{VID}/events"
QUERY = b"material_key=prusament-pla"
SOON = 2.0


class Announcer:
    def __init__(self) -> None:
        self.listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def finished(self, job: JobSpec) -> None:
        for listener in list(self.listeners):
            listener(job)


class FakeScorecard:
    def __init__(self) -> None:
        self.card: ScorecardSnapshot | Exception = NotScored(VID)
        self.reads = 0

    def __call__(self, tenant: Tenant, arguments: ScorecardInput) -> ScorecardSnapshot:
        self.reads += 1
        if isinstance(self.card, Exception):
            raise self.card
        return self.card

    def becomes(self, material_key: str) -> ScorecardSnapshot:
        self.card = snapshot(reported(material_key))
        return self.card


class StreamedResponse:
    def __init__(self, messages: anyio.abc.ObjectReceiveStream[MutableMapping[str, Any]]) -> None:
        self._messages = messages
        self._text = ""
        self.status = 0
        self.headers: dict[str, str] = {}

    async def start(self) -> None:
        with anyio.fail_after(SOON):
            start = await self._messages.receive()
        self.status = start["status"]
        self.headers = {k.decode(): v.decode() for k, v in start["headers"]}

    async def frame(self, within: float = SOON) -> str | None:
        with anyio.move_on_after(within):
            while "\n\n" not in self._text:
                message = await self._messages.receive()
                self._text += message.get("body", b"").decode()
            frame, _, self._text = self._text.partition("\n\n")
            return frame
        return None

    async def whole(self) -> str:
        with anyio.fail_after(SOON):
            while True:
                message = await self._messages.receive()
                self._text += message.get("body", b"").decode()
                if not message.get("more_body", False):
                    return self._text

    async def card(self, within: float = SOON) -> dict[str, Any] | None:
        frame = await self.frame(within)
        if frame is None:
            return None
        fields = dict(line.split(": ", 1) for line in frame.splitlines())
        assert fields["event"] == "scorecard"
        body: dict[str, Any] = json.loads(fields["data"])
        assert fields["id"] == body["etag"]
        return body


@asynccontextmanager
async def opened(
    app: Starlette, token: str = "ok", path: str = PATH, query: bytes = QUERY
) -> AsyncGenerator[StreamedResponse]:
    sent, received = anyio.create_memory_object_stream[MutableMapping[str, Any]](100)
    gone = anyio.Event()

    async def receive() -> MutableMapping[str, Any]:
        await gone.wait()
        return {"type": "http.disconnect"}

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": [(b"cookie", f"__session={token}".encode()), (b"host", b"127.0.0.1")],
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 50000),
    }
    async with anyio.create_task_group() as group:
        group.start_soon(app, scope, receive, sent.send)
        response = StreamedResponse(received)
        await response.start()
        try:
            yield response
        finally:
            gone.set()


def job(tenant: Tenant, variant_id: str = VID) -> JobSpec:
    return JobSpec(
        tenant.variants,
        variant_id,
        "b" * 64,
        SPECS,
        Quick(),
        build_request("prusament-pla", load_materials()),
    )


@pytest.fixture
def tenant(tmp_path: Path) -> Tenant:
    return Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest).of(ALICE)


def app_of(
    tenant: Tenant,
    lanes: Announcer,
    store: FakeScorecard,
    hooked: bool = True,
    signed_in: str = "ok",
    expires: list[str] | None = None,
) -> Starlette:
    def person(token: str) -> PersonSession | None:
        if token != signed_in or (expires is not None and token in expires):
            return None
        return PersonSession(account=ALICE, session_id="sess")

    route: Route = events_route(person, lambda _: tenant, lanes, store, hooked)
    return Starlette(routes=[route])


async def test_a_stream_opens_with_the_card_as_it_stands_and_the_etag_as_its_id(
    tenant: Tenant,
) -> None:
    store = FakeScorecard()
    first = store.becomes("prusament-pla")
    async with opened(app_of(tenant, Announcer(), store)) as stream:
        assert stream.status == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert stream.headers["cache-control"] == "no-store"
        body = await stream.card()
    assert body == first.model_dump(by_alias=True, mode="json")


async def test_each_job_that_stores_a_result_sends_the_whole_card_it_changed(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    pending = store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert (await stream.card()) is not None
        done = store.becomes("generic-petg")
        lanes.finished(job(tenant))
        body = await stream.card(0.4)
    assert body == done.model_dump(by_alias=True, mode="json")
    assert body is not None
    assert body["etag"] != pending.etag


async def test_a_job_that_finishes_during_the_first_read_reaches_the_stream_at_once(
    tenant: Tenant,
) -> None:
    lanes = Announcer()
    store = FakeScorecard()
    first = store.becomes("prusament-pla")

    class FinishesDuringTheFirstRead(FakeScorecard):
        def __call__(self, tenant: Tenant, arguments: ScorecardInput) -> ScorecardSnapshot:
            card = store(tenant, arguments)
            if store.reads == 1:
                store.becomes("generic-petg")
                lanes.finished(job(tenant))
            return card

    async with opened(app_of(tenant, lanes, FinishesDuringTheFirstRead())) as stream:
        sent = await stream.card()
        assert sent is not None and sent["etag"] == first.etag
        updated = await stream.card(0.4)
    assert updated is not None
    assert updated["etag"] != first.etag


async def test_a_stream_ends_once_its_session_token_stops_being_accepted(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    expired: list[str] = []
    async with opened(app_of(tenant, lanes, store, expires=expired)) as stream:
        assert (await stream.card()) is not None
        expired.append("ok")
        store.becomes("generic-petg")
        lanes.finished(job(tenant))
        frame = await stream.frame(0.4)
    assert frame is not None
    assert "event: refused" in frame
    assert "SignedOut" in frame
    assert "event: scorecard" not in frame


async def test_a_finished_job_that_changed_nothing_sends_no_second_copy(tenant: Tenant) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert (await stream.card()) is not None
        lanes.finished(job(tenant))
        assert await stream.frame(0.3) is None


async def test_a_job_of_another_variant_or_another_account_does_not_wake_the_stream(
    tenant: Tenant, tmp_path: Path
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert (await stream.card()) is not None
        reads = store.reads
        lanes.finished(job(tenant, "fedcba9876543210"))
        other = Tenants(tmp_path / "other", 60, Door(wait_seconds=0.3), ingest).of(
            AccountId("user_bob")
        )
        lanes.finished(job(other))
        await asyncio.sleep(0.2)
    assert store.reads == reads


async def test_a_variant_nobody_scored_yet_holds_the_stream_open_and_sends_its_first_card(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert stream.status == 200
        assert await stream.frame(0.3) is None
        scored = store.becomes("prusament-pla")
        lanes.finished(job(tenant))
        body = await stream.card(0.4)
    assert body is not None
    assert body["etag"] == scored.etag


async def test_with_the_hook_off_the_card_still_arrives_by_the_half_second_read(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store, hooked=False)) as stream:
        assert (await stream.card()) is not None
        assert lanes.listeners == []
        done = store.becomes("generic-petg")
        body = await stream.card(events.POLL_SECONDS * 2)
    assert body is not None
    assert body["etag"] == done.etag


async def test_the_stream_stops_listening_when_the_client_goes(tenant: Tenant) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert (await stream.card()) is not None
        assert len(lanes.listeners) == 1
    with anyio.fail_after(SOON):
        while lanes.listeners:
            await anyio.sleep(0.01)


async def test_a_variant_of_another_account_is_not_found_and_sends_no_card(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.card = UnknownVariant(VID)
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert stream.status == 404
        body = await stream.whole()
    assert "UnknownVariant" in body
    assert "event: scorecard" not in body
    assert lanes.listeners == []


async def test_a_material_key_no_table_row_names_is_refused_as_the_scorecard_route_refuses(
    tenant: Tenant,
) -> None:
    lanes = Announcer()
    unknown = b"material_key=unobtanium"
    async with opened(app_of(tenant, lanes, FakeScorecard()), query=unknown) as stream:
        assert stream.status == 400
        body = await stream.whole()
    assert "NotScored" in body
    assert "event: scorecard" not in body
    assert lanes.listeners == []


async def test_a_request_without_a_person_session_is_refused_before_anything_is_read(
    tenant: Tenant,
) -> None:
    store = FakeScorecard()
    async with opened(app_of(tenant, Announcer(), store), token="an agent token") as stream:
        assert stream.status == 401
        assert "sign in" in await stream.whole()
    assert store.reads == 0


async def test_a_card_whose_variant_turns_out_unreadable_ends_the_stream_with_a_refusal(
    tenant: Tenant,
) -> None:
    store, lanes = FakeScorecard(), Announcer()
    store.becomes("prusament-pla")
    async with opened(app_of(tenant, lanes, store)) as stream:
        assert (await stream.card()) is not None
        store.card = UnknownVariant(VID)
        lanes.finished(job(tenant))
        assert await stream.frame(0.4) == "event: refused\ndata: UnknownVariant"
        assert await stream.frame(0.2) is None


async def test_through_the_hosted_app_only_the_owner_of_a_variant_opens_its_stream(
    tmp_path: Path,
) -> None:
    local = LocalIssuer.open(tmp_path, BASE)
    tenants = Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest)
    code = "result = None"
    variant_id = entry.variant_id(code, image_tag(BUILD))
    entry.save(
        tenants.of(ALICE).variants, variant_id, code, Build(outcome=Built(), output=""), b"step"
    )
    app = build_app(local.issuer(), tenants, LocalSignIn(local))
    path = f"/v1/variants/{variant_id}/events"
    async with opened(app, local.mint_person("user_alice"), path) as mine:
        assert mine.status == 200
        assert await mine.frame(0.3) is None
    async with opened(app, local.mint_person("user_bob"), path) as theirs:
        assert theirs.status == 404
        assert "UnknownVariant" in await theirs.whole()
    async with opened(app, local.mint_agent("user_alice"), path) as agent:
        assert agent.status == 401


def test_the_bell_may_ring_from_any_thread_and_after_the_loop_is_gone(tenant: Tenant) -> None:
    loop = asyncio.new_event_loop()
    wake = loop.run_until_complete(_wake(tenant))
    loop.close()
    ringer = threading.Thread(target=wake, args=(job(tenant),))
    ringer.start()
    ringer.join()


async def _wake(tenant: Tenant) -> events.Wake:
    return events.Wake(tenant, VID)

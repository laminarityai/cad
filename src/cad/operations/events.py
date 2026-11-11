"""GET /v1/variants/{variant_id}/events: one variant's scorecard as server-sent events.

The first event is the card as the signed results hold it when the stream opens, and every later
event is a whole `ScorecardSnapshot` that differs from the one before. Each job that stores a
result wakes the stream, so a card turns from pending to done at once. A slower store read runs
beside it, for what no job announces (a confirmation, a researched value), and as the only path
when the hook is switched off. A variant nobody has scored yet is not refused: the stream stays
open and sends nothing until its first check stores a result. A material_key that names no row of
the brief's table, no material the user confirmed and no material the agent chose for the variant's
slot gets the scorecard route's refusal instead.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from typing import Final, Protocol

import anyio
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from cad.checks.jobs import JobSpec
from cad.checks.lanes import LANES, Listener
from cad.errors import Refused, Unavailable
from cad.operations.model import Tenant
from cad.operations.routes import (
    PersonOf,
    TenantOf,
    refusal,
    refuse,
    session_person,
    session_token,
)
from cad.operations.scorecards import ScorecardInput, names_a_material, scorecard
from cad.sandbox.meter import metered
from cad.scorecard.material import ScorecardSnapshot
from cad.scorecard.score import NotScored

EVENTS_PATH: Final = "/v1/variants/{variant_id}/events"
POLL_SECONDS: Final = 0.5
SAFETY_SECONDS: Final = 5.0
HEARTBEAT_SECONDS: Final = 15.0
HEADERS: Final = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}

type SnapshotOf = Callable[[Tenant, ScorecardInput], ScorecardSnapshot]


class Announces(Protocol):
    def subscribe(self, listener: Listener) -> Callable[[], None]: ...


class Wake:
    def __init__(self, tenant: Tenant, variant_id: str) -> None:
        self._loop = asyncio.get_running_loop()
        self._bell = asyncio.Event()
        self._tenant, self._variant_id = tenant, variant_id

    def __call__(self, job: JobSpec) -> None:
        if (job.root, job.variant_id) == (self._tenant.variants, self._variant_id):
            with suppress(RuntimeError):
                self._loop.call_soon_threadsafe(self._bell.set)

    def reset(self) -> None:
        self._bell.clear()

    async def rung(self, within: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._bell.wait(), within)


def events_route(
    person_of: PersonOf,
    tenant_of: TenantOf,
    lanes: Announces = LANES,
    snapshot_of: SnapshotOf = scorecard,
    hooked: bool = True,
) -> Route:
    async def endpoint(request: Request) -> Response:
        person = session_person(person_of, request)
        if isinstance(person, Response):
            return person
        tenant = tenant_of(person.account)
        try:
            arguments = ScorecardInput.model_validate(
                {**request.query_params, **request.path_params}
            )
        except ValidationError as invalid:
            return refuse(422, str(invalid))

        async def read() -> ScorecardSnapshot | None:
            def run() -> ScorecardSnapshot | None:
                try:
                    with metered(tenant.meter):
                        return snapshot_of(tenant, arguments)
                except NotScored:
                    if names_a_material(tenant, arguments):
                        return None
                    raise

            return await anyio.to_thread.run_sync(run)

        wake = Wake(tenant, arguments.variant_id)
        unsubscribe = lanes.subscribe(wake) if hooked else None
        try:
            first = await read()
        except BaseException as error:
            if unsubscribe is not None:
                unsubscribe()
            if not isinstance(error, Refused | Unavailable):
                raise
            return refusal(error)
        return StreamingResponse(
            _events(
                read,
                lambda: person_of(session_token(request)) is not None,
                wake,
                first,
                SAFETY_SECONDS if hooked else POLL_SECONDS,
                unsubscribe,
            ),
            media_type="text/event-stream",
            headers=HEADERS,
        )

    return Route(EVENTS_PATH, endpoint, methods=["GET"], name="scorecard_events")


async def _events(
    read: Callable[[], Awaitable[ScorecardSnapshot | None]],
    signed_in: Callable[[], bool],
    wake: Wake,
    first: ScorecardSnapshot | None,
    interval: float,
    unsubscribe: Callable[[], None] | None,
) -> AsyncIterator[str]:
    sent, quiet = "", time.monotonic()
    card = first
    try:
        while True:
            if card is not None and card.etag != sent:
                sent, quiet = card.etag, time.monotonic()
                yield _frame(card)
            elif time.monotonic() - quiet >= HEARTBEAT_SECONDS:
                quiet = time.monotonic()
                yield ": keep-alive\n\n"
            await wake.rung(interval)
            wake.reset()
            if not signed_in():
                yield "event: refused\ndata: SignedOut\n\n"
                return
            try:
                card = await read()
            except (Refused, Unavailable) as refused:
                yield f"event: refused\ndata: {type(refused).__name__}\n\n"
                return
    finally:
        if unsubscribe is not None:
            unsubscribe()


def _frame(card: ScorecardSnapshot) -> str:
    body = TypeAdapter(ScorecardSnapshot).dump_json(card, by_alias=True).decode()
    return f"id: {card.etag}\nevent: scorecard\ndata: {body}\n\n"

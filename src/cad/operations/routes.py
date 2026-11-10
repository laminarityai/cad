"""The HTTP adapter for the person: a route runs one registry operation for the signed-in person.

A route accepts only a Clerk session token, from the `__session` cookie or an `Authorization:
Bearer` header, so an agent's OAuth access token gets 401 here, as a session token does on `/mcp`.
"""

import hashlib
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final, cast

import anyio
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from cad.accounts.principal import AccountId, PersonSession
from cad.briefs.store import UnknownBrief
from cad.operations.model import Audience, Operation, Tenant
from cad.operations.tools import REFUSALS, UNAVAILABLE
from cad.projects.model import UnknownProject
from cad.sandbox.meter import metered
from cad.variants.entry import UnknownVariant

SESSION_COOKIE: Final = "__session"
CHALLENGE: Final = {"WWW-Authenticate": 'Bearer realm="cad", error="invalid_token"'}
NOT_FOUND: Final = (UnknownVariant, UnknownBrief, UnknownProject)
IMMUTABLE: Final = "private, max-age=31536000, immutable"

type PersonOf = Callable[[str], PersonSession | None]
type TenantOf = Callable[[AccountId], Tenant]


@dataclass(frozen=True, slots=True)
class Served:
    path: str
    immutable: bool = False


def person_routes(
    operations: Iterable[Operation],
    served: Mapping[str, Served],
    person_of: PersonOf,
    tenant_of: TenantOf,
) -> list[Route]:
    reachable = [one for one in operations if Audience.PERSON in one.audience]
    names = {one.name for one in reachable}
    if names != set(served):
        raise ValueError(
            f"routes and person operations differ: {sorted(names ^ set(served))} lack a partner"
        )
    return [person_route(served[one.name], one, person_of, tenant_of) for one in reachable]


def person_route(served: Served, one: Operation, person_of: PersonOf, tenant_of: TenantOf) -> Route:
    if Audience.PERSON not in one.audience:
        raise ValueError(f"{one.name} is not for the person, so it has no web route")

    async def endpoint(request: Request) -> Response:
        person = person_of(session_token(request))
        if person is None:
            return _error(401, "sign in: this route takes a Clerk session token", CHALLENGE)
        tenant = tenant_of(person.account)
        try:
            arguments = one.input.model_validate({**request.query_params, **request.path_params})
        except ValidationError as error:
            return _error(422, str(error))

        def run() -> object:
            with metered(tenant.meter):
                return one.run(tenant, arguments)

        try:
            if one.is_async:
                with metered(tenant.meter):
                    result = await cast(Awaitable[object], one.run(tenant, arguments))
            else:
                result = await anyio.to_thread.run_sync(run)
        except NOT_FOUND as error:
            return _error(404, f"{type(error).__name__}: {error}")
        except REFUSALS as error:
            return _error(400, f"{type(error).__name__}: {error}")
        except UNAVAILABLE as error:
            return _error(503, str(error))
        body = _body(one, result)
        if not served.immutable:
            return Response(body, media_type="application/json")
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        headers = {"ETag": etag, "Cache-Control": IMMUTABLE}
        if _matches(request, etag):
            return Response(status_code=304, headers=headers)
        return Response(body, media_type="application/json", headers=headers)

    return Route(served.path, endpoint, methods=["GET"], name=one.name)


def _body(one: Operation, result: object) -> bytes:
    adapter = TypeAdapter[object](cast(type[object], one.output))
    return adapter.dump_json(result, by_alias=True)


def _matches(request: Request, etag: str) -> bool:
    """If-None-Match compares weakly (RFC 9110 13.1.2), so `W/"x"` matches `"x"`, and `*` matches
    any stored body."""
    asked = [
        tag.strip().removeprefix("W/")
        for tag in request.headers.get("if-none-match", "").split(",")
    ]
    return "*" in asked or etag in asked


def session_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return request.cookies.get(SESSION_COOKIE, "")


def _error(status: int, message: str, headers: dict[str, str] | None = None) -> Response:
    return JSONResponse({"error": message}, status, headers=headers)

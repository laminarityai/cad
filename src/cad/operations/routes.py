"""The HTTP adapter for the person: a route runs one registry operation for the signed-in person.

A route accepts only a Clerk session token, from the `__session` cookie or an `Authorization:
Bearer` header, so an agent's OAuth access token gets 401 here, as a session token does on `/mcp`.
"""

import hashlib
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Final, cast

import anyio
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from cad.accounts.principal import AccountId, PersonSession
from cad.errors import NotFound, Refused, Unavailable
from cad.operations.model import Audience, Download, Operation, Tenant
from cad.sandbox.meter import metered

SESSION_COOKIE: Final = "__session"
CHALLENGE: Final = {"WWW-Authenticate": 'Bearer realm="cad", error="invalid_token"'}
IMMUTABLE: Final = "private, max-age=31536000, immutable"
FILE_TYPE: Final = "application/octet-stream"

type PersonOf = Callable[[str], PersonSession | None]
type TenantOf = Callable[[AccountId], Tenant]


@dataclass(frozen=True, slots=True)
class Served:
    path: str
    immutable: bool = False
    method: str = "GET"
    download: bool = False
    """The operation returns a `Download`, and the route sends its bytes as an attachment."""


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
    if served.download != (one.output is Download):
        raise ValueError(f"{one.name} is a download exactly when its output is a Download")

    async def endpoint(request: Request) -> Response:
        person = session_person(person_of, request)
        if isinstance(person, Response):
            return person
        tenant = tenant_of(person.account)
        sent = (
            await _request_body(request) if served.method != "GET" else dict(request.query_params)
        )
        if sent is None:
            return refuse(422, "the request body is not a JSON object")
        try:
            arguments = one.input.model_validate({**sent, **request.path_params})
        except ValidationError as error:
            return refuse(422, str(error))

        def run() -> object:
            with metered(tenant.meter):
                return one.run(tenant, arguments)

        try:
            if one.is_async:
                with metered(tenant.meter):
                    result = await cast(Awaitable[object], one.run(tenant, arguments))
            else:
                result = await anyio.to_thread.run_sync(run)
        except (Refused, Unavailable) as error:
            return refusal(error)
        if isinstance(result, Download):
            body, media_type = result.data, FILE_TYPE
            attached = {"Content-Disposition": f'attachment; filename="{result.filename}"'}
        else:
            body, media_type, attached = _body(one, result), "application/json", {}
        if not served.immutable:
            return Response(body, media_type=media_type, headers=attached)
        etag = f'"{hashlib.sha256(body).hexdigest()}"'
        headers = {"ETag": etag, "Cache-Control": IMMUTABLE}
        if _matches(request, etag):
            return Response(status_code=304, headers=headers)
        return Response(body, media_type=media_type, headers={**headers, **attached})

    return Route(served.path, endpoint, methods=[served.method], name=one.name)


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


async def _request_body(request: Request) -> dict[str, object] | None:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        return None
    return cast(dict[str, object], parsed) if isinstance(parsed, dict) else None


def session_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return request.cookies.get(SESSION_COOKIE, "")


def session_person(person_of: PersonOf, request: Request) -> PersonSession | Response:
    """The signed-in person, or the 401 a route answers when the request carries no valid Clerk
    session token."""
    person = person_of(session_token(request))
    if person is None:
        return refuse(401, "sign in: this route takes a Clerk session token", CHALLENGE)
    return person


def refusal(error: Refused | Unavailable) -> Response:
    if isinstance(error, Unavailable):
        return refuse(503, str(error))
    status = 404 if isinstance(error, NotFound) else 400
    return refuse(status, f"{type(error).__name__}: {error}")


def refuse(status: int, message: str, headers: dict[str, str] | None = None) -> Response:
    return JSONResponse({"error": message}, status, headers=headers)

"""The HTTP adapter for the person: a route runs one registry operation for the signed-in person.

A route accepts only a Clerk session token, from the `__session` cookie or an `Authorization:
Bearer` header, so an agent's OAuth access token gets 401 here, as a session token does on `/mcp`.
"""

from collections.abc import Awaitable, Callable
from typing import Final, cast

import anyio
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from cad.accounts.principal import AccountId, PersonSession
from cad.operations.model import Audience, Operation, Tenant
from cad.operations.tools import REFUSALS, UNAVAILABLE
from cad.sandbox.meter import metered

SESSION_COOKIE: Final = "__session"
CHALLENGE: Final = {"WWW-Authenticate": 'Bearer realm="cad", error="invalid_token"'}

type PersonOf = Callable[[str], PersonSession | None]
type TenantOf = Callable[[AccountId], Tenant]


def person_route(path: str, one: Operation, person_of: PersonOf, tenant_of: TenantOf) -> Route:
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
        except REFUSALS as error:
            return _error(400, f"{type(error).__name__}: {error}")
        except UNAVAILABLE as error:
            return _error(503, str(error))
        return JSONResponse(cast(BaseModel, result).model_dump(mode="json", by_alias=True))

    return Route(path, endpoint, methods=["GET"], name=one.name)


def session_token(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return request.cookies.get(SESSION_COOKIE, "")


def _error(status: int, message: str, headers: dict[str, str] | None = None) -> Response:
    return JSONResponse({"error": message}, status, headers=headers)

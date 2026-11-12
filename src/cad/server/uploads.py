"""The person-only routes that add a file to a project and decline an uploaded part (ADR-0012).

An upload is the person's confirmation, so only a person session reaches these routes and no
MCP tool does. The file comes as the raw body with `Content-Type: application/octet-stream`, and
the decline as JSON. Neither is a type a page on another origin can send without a preflight,
which this server never answers, so another site cannot upload or decline for the person.
"""

import json
from collections.abc import Callable

import anyio
from pydantic import BaseModel, ValidationError
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from cad.accounts.principal import PersonSession
from cad.context_parts.ids import ContextPartId
from cad.errors import Refused, Unavailable
from cad.operations.model import Tenant
from cad.operations.openapi import OCTETS
from cad.operations.routes import CHALLENGE, PersonOf, TenantOf, refusal, refuse, session_token
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId, ProjectRefused, parse_project_id
from cad.sandbox.meter import metered
from cad.uploads import store
from cad.uploads.model import kind_of
from cad.uploads.views import document_view, part_view
from cad.uploads.web import PATHS, Added, AddFileInput, Declined, DeclineInput
from cad.variants.entry import MAX_FILE_BYTES


def upload_routes(person_of: PersonOf, tenant_of: TenantOf) -> list[Route]:
    def signed_in(request: Request) -> tuple[PersonSession, Tenant, ProjectId] | Response:
        person = person_of(session_token(request))
        if person is None:
            return refuse(401, "sign in: this route takes a Clerk session token", CHALLENGE)
        tenant = tenant_of(person.account)
        try:
            project = parse_project_id(request.path_params["project_id"])
        except ProjectRefused as error:
            return refuse(404, str(error))
        if not project_briefs(tenant.roots, project):
            return refuse(404, f"no project {project} is stored")
        return person, tenant, project

    async def add(request: Request) -> Response:
        found = signed_in(request)
        if isinstance(found, Response):
            return found
        person, tenant, project = found
        if _content_type(request) != OCTETS:
            return refuse(415, f"send the file's bytes as {OCTETS}")
        try:
            sent = AddFileInput.model_validate({**request.query_params, **request.path_params})
        except ValidationError as error:
            return refuse(422, str(error))
        data = await _body(request)
        if data is None:
            return refuse(413, f"a file is at most {MAX_FILE_BYTES // (1024 * 1024)} MB")
        name, unit = sent.name.strip(), sent.unit

        def run() -> Added:
            kind = kind_of(name)
            projects = tenant.roots.projects
            if kind.cad is None:
                document = store.add_document(projects, project, name, kind, data, person)
                return Added(kind="document", document=document_view(document))
            with metered(tenant.meter):
                part = store.add_part(
                    projects, project, name, kind, unit, data, person, tenant.ingest
                )
            return Added(kind="part", part=part_view(part))

        return await _answered(run)

    async def decline(request: Request) -> Response:
        found = signed_in(request)
        if isinstance(found, Response):
            return found
        person, tenant, project = found
        if _content_type(request) != "application/json":
            return refuse(415, "send application/json")
        try:
            body = json.loads(await request.body() or b"{}")
            sent = DeclineInput.model_validate({**body, **request.path_params})
        except (ValueError, TypeError) as error:
            return refuse(422, str(error))
        part = sent.part_id

        def run() -> Declined:
            done = store.decline_part(
                tenant.roots.projects, project, ContextPartId(part), sent.note, person
            )
            if done:
                tenant.bell.ring()
            return Declined(part_id=part, declined=done)

        return await _answered(run)

    return [
        Route(PATHS["add_file"], add, methods=["POST"], name="add_file"),
        Route(PATHS["decline_part"], decline, methods=["POST"], name="decline_part"),
    ]


async def _answered(run: Callable[[], BaseModel]) -> Response:
    try:
        result = await anyio.to_thread.run_sync(run)
    except (Refused, Unavailable) as error:
        return refusal(error)
    return Response(result.model_dump_json(), media_type="application/json")


def _content_type(request: Request) -> str:
    return request.headers.get("content-type", "").split(";")[0].strip()


async def _body(request: Request) -> bytes | None:
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_FILE_BYTES:
        return None
    read = bytearray()
    async for chunk in request.stream():
        read += chunk
        if len(read) > MAX_FILE_BYTES:
            return None
    return bytes(read)

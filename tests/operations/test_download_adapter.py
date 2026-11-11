import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from cad.accounts.principal import AccountId, PersonSession
from cad.operations.model import Audience, Download, Input, Tenant, operation
from cad.operations.routes import Served, person_route
from cad.operations.tenants import Tenants

ALICE = AccountId("user_alice")
BYTES = bytes(range(256)) + b"\r\n\x00 not utf-8: \xff\xfe"


class Which(Input):
    stem: str


def send(tenant: Tenant, arguments: Which) -> Download:
    del tenant
    return Download(filename=f"{arguments.stem}.bin", data=BYTES)


def not_a_download(tenant: Tenant, arguments: Which) -> dict[str, str]:
    del tenant, arguments
    return {}


def person_of(token: str) -> PersonSession | None:
    return PersonSession(account=ALICE, session_id="s") if token == "ok" else None


def served(tenants: Tenants, immutable: bool) -> TestClient:
    one = operation(
        name="file",
        audience=Audience.PERSON,
        description="a file",
        input=Which,
        output=Download,
        run=send,
    )
    route = person_route(
        Served("/file/{stem}", immutable=immutable, download=True), one, person_of, tenants.of
    )
    return TestClient(Starlette(routes=[route]), cookies={"__session": "ok"})


def test_a_download_sends_the_bytes_as_they_are_under_an_attachment_header(
    tenants: Tenants,
) -> None:
    sent = served(tenants, immutable=False).get("/file/desk-box-rev1")
    assert sent.content == BYTES
    assert sent.headers["Content-Type"] == "application/octet-stream"
    assert sent.headers["Content-Disposition"] == 'attachment; filename="desk-box-rev1.bin"'
    assert "Cache-Control" not in sent.headers


def test_an_immutable_download_keeps_its_etag_and_cache_header_and_a_matching_etag_gets_304(
    tenants: Tenants,
) -> None:
    http = served(tenants, immutable=True)
    first = http.get("/file/a")
    again = http.get("/file/a", headers={"If-None-Match": first.headers["ETag"]})
    assert "immutable" in first.headers["Cache-Control"]
    assert first.headers["Content-Disposition"] == 'attachment; filename="a.bin"'
    assert (again.status_code, again.content) == (304, b"")
    assert again.headers["ETag"] == first.headers["ETag"]


def test_a_route_and_an_operation_must_agree_on_whether_it_is_a_download(tenants: Tenants) -> None:
    one = operation(
        name="file",
        audience=Audience.PERSON,
        description="a file",
        input=Which,
        output=Download,
        run=send,
    )
    plain = operation(
        name="plain",
        audience=Audience.PERSON,
        description="json",
        input=Which,
        output=Which,
        run=not_a_download,
    )
    with pytest.raises(ValueError, match="exactly when"):
        person_route(Served("/file/{stem}"), one, person_of, tenants.of)
    with pytest.raises(ValueError, match="exactly when"):
        person_route(Served("/plain/{stem}", download=True), plain, person_of, tenants.of)

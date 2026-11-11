import re
import subprocess
import sys
from pathlib import Path
from typing import Final, cast

import pytest
from starlette.routing import Route

from cad.accounts.local import LocalIssuer
from cad.confirmations.waiting import Door
from cad.confirmations.web import LocalSignIn
from cad.context_parts.ingest import ingest
from cad.operations.model import Audience
from cad.operations.openapi import Described, Json, document, from_registry
from cad.operations.outside import HAND_DESCRIBED, every_route
from cad.operations.reads import VariantInput, VariantView
from cad.operations.registry import OPERATIONS, ROUTES
from cad.operations.tenants import Tenants
from cad.server.hosted import build_app

ROOT = Path(__file__).resolve().parents[2]
SKIPPED = {"HEAD", "OPTIONS"}
NOT_API: Final = {
    ("*", "/mcp"): "the MCP transport; its tools are described by the tool list",
    ("GET", "/.well-known/oauth-protected-resource/mcp"): "RFC 9728 metadata for MCP clients",
    ("GET", "/projects/{project_id}/confirm"): "the confirmation page, HTML for the browser",
    ("POST", "/projects/{project_id}/confirm"): "the confirmation page's form post",
    ("GET", "/local/sign-in"): "the local server's sign-in redirect, never hosted",
    ("GET", "/"): "redirects to the web app",
    ("GET", "/app"): "redirects to the web app",
    ("GET", "/app/"): "the web app's static files",
    ("GET", "/app/{path:path}"): "the web app's static files",
}
DOCUMENT = document(every_route())
PATHS = cast(dict[str, dict[str, Json]], DOCUMENT["paths"])


def described() -> dict[tuple[str, str], Json]:
    return {
        (method.upper(), path): one for path, item in PATHS.items() for method, one in item.items()
    }


def parameters(one: Json) -> list[Json]:
    return cast(list[Json], one.get("parameters", []))


def test_each_person_operation_has_exactly_one_path_and_no_agent_only_operation_has_any() -> None:
    names = [cast(str, one["operationId"]) for one in described().values()]
    person = {one.name for one in OPERATIONS if Audience.PERSON in one.audience}
    agent_only = {one.name for one in OPERATIONS if one.audience == Audience.AGENT}
    assert sorted(names) == sorted(person | {one.name for one in HAND_DESCRIBED})
    assert agent_only
    assert not agent_only & set(names)


def test_each_path_has_the_method_and_template_its_route_has() -> None:
    registry = {(served.method, served.path) for served in ROUTES.values()}
    assert set(described()) == registry | {(one.method, one.path) for one in HAND_DESCRIBED}


def test_every_web_route_the_app_mounts_is_described(tmp_path: Path) -> None:
    local = LocalIssuer.open(tmp_path, "http://127.0.0.1:8765")
    app = build_app(
        local.issuer(),
        Tenants(tmp_path / "accounts", 60, Door(wait_seconds=0.3), ingest),
        LocalSignIn(local),
    )
    mounted = {
        (method, route.path)
        for route in app.router.routes
        if isinstance(route, Route)
        for method in (route.methods or {"*"}) - SKIPPED
    }
    assert mounted - set(NOT_API) == set(described()), (
        "describe a new route in the registry ROUTES or in cad.operations.outside.HAND_DESCRIBED"
    )
    assert set(NOT_API) <= mounted


def test_a_templated_name_is_a_path_parameter_and_every_other_argument_is_not() -> None:
    for (method, path), one in described().items():
        templated = set(re.findall(r"{(\w+)}", path))
        in_path = {item["name"] for item in parameters(one) if item["in"] == "path"}
        assert in_path == templated, path
        elsewhere = {item["in"] for item in parameters(one)} - {"path"}
        assert elsewhere <= ({"query"} if method == "GET" else set()), path


def test_a_put_carries_its_remaining_argument_in_a_json_body() -> None:
    one = described()[("PUT", "/v1/conversations/{conversation_id}/mode")]
    body = cast(Json, one["requestBody"])
    schema = cast(Json, cast(Json, cast(Json, body["content"])["application/json"])["schema"])
    assert list(cast(Json, schema["properties"])) == ["mode"]
    assert schema["required"] == ["mode"]


def test_a_mesh_names_its_etag_and_a_304_and_a_scorecard_does_not() -> None:
    mesh = cast(
        Json, described()[("GET", "/v1/geometry/{version}/{brep_sha256}.json")]["responses"]
    )
    card = cast(Json, described()[("GET", "/v1/variants/{variant_id}/scorecard")]["responses"])
    assert "304" in mesh
    assert "ETag" in cast(Json, cast(Json, mesh["200"])["headers"])
    assert "304" not in card


def test_a_download_is_an_octet_stream_that_names_its_attachment_header_and_no_schema() -> None:
    file = described()[("GET", "/v1/exports/{version}/{brep_sha256}.{format}")]
    ok = cast(Json, cast(Json, file["responses"])["200"])
    content = cast(Json, ok["content"])
    assert content == {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }
    assert {"Content-Disposition", "ETag", "Cache-Control"} <= set(cast(Json, ok["headers"]))
    assert "304" in cast(Json, file["responses"])
    assert "Download" not in cast(Json, cast(Json, DOCUMENT["components"])["schemas"])


def test_an_input_model_is_not_a_schema_but_every_reference_resolves() -> None:
    schemas = cast(dict[str, Json], cast(Json, DOCUMENT["components"])["schemas"])
    assert not [name for name in schemas if name.endswith("Input")]
    spelled = set(re.findall(r'"#/components/schemas/([^"]+)"', repr(DOCUMENT).replace("'", '"')))
    assert spelled <= set(schemas)


def test_a_route_with_no_operation_or_an_operation_with_no_route_is_refused() -> None:
    with pytest.raises(ValueError, match="differ"):
        from_registry(OPERATIONS, {})
    with pytest.raises(ValueError, match="differ"):
        from_registry([], ROUTES)


def test_a_path_template_naming_no_argument_is_refused() -> None:
    stray = Described(
        name="stray",
        path="/v1/stray/{nothing}",
        method="GET",
        input=VariantInput,
        output=VariantView,
    )
    with pytest.raises(ValueError, match="nothing"):
        document([stray])


def test_the_step_says_what_to_install_when_node_is_missing(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "gen_ts.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": str(tmp_path)},
    )
    assert done.returncode == 1
    assert "node" in done.stdout.lower()
    assert "Install Node" in done.stdout

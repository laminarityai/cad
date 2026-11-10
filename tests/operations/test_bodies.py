from collections.abc import AsyncIterator
from pathlib import Path

import httpx2
import pytest
from jsonschema import ValidationError
from starlette.applications import Starlette

from cad.accounts.local import LocalIssuer
from cad.accounts.principal import AccountId
from cad.accounts.tenants import Tenants
from cad.confirmations.ballot import OS_OPEN
from cad.context_parts.ingest import ingest
from cad.operations.scorecards import ScoreVariantInput, score_variant
from cad.operations.variants import BuildVariantInput, build_variant
from cad.server.hosted import build_app
from tests.operations.bodies import check

pytestmark = pytest.mark.anyio

BASE = "http://127.0.0.1:8765"
ALICE = AccountId("user_alice")
PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
KEY = "prusament-pla"
UNSTORED = "0123456789abcdef"


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[tuple[Starlette, LocalIssuer, Tenants]]:
    local = LocalIssuer.open(tmp_path, BASE)
    tenants = Tenants(tmp_path / "accounts", 60, OS_OPEN, 0.3, ingest)
    made = build_app(local.issuer(), tenants)
    async with made.router.lifespan_context(made):
        yield made, local, tenants


async def test_what_the_routes_send_for_a_scored_variant_is_what_the_types_say(
    app: tuple[Starlette, LocalIssuer, Tenants],
) -> None:
    made, local, tenants = app
    alice = tenants.of(ALICE)
    vid = build_variant(alice, BuildVariantInput(code=PLATE)).variant_id
    score_variant(alice, ScoreVariantInput(variant_id=vid, material_key=KEY))
    asked: list[tuple[str, str, dict[str, str]]] = [
        ("/v1/server", "/v1/server", {}),
        ("/v1/materials", "/v1/materials", {}),
        ("/v1/projects", "/v1/projects", {}),
        ("/v1/variants/{variant_id}", f"/v1/variants/{vid}", {}),
        (
            "/v1/variants/{variant_id}/scorecard",
            f"/v1/variants/{vid}/scorecard",
            {"material_key": KEY},
        ),
        ("/v1/variants/{variant_id}", f"/v1/variants/{UNSTORED}", {}),
    ]
    transport = httpx2.ASGITransport(app=made)
    cookies = {"__session": local.mint_person(ALICE)}
    async with httpx2.AsyncClient(transport=transport, base_url=BASE, cookies=cookies) as http:
        sent = [(template, await http.get(path, params=query)) for template, path, query in asked]
    for template, one in sent:
        check("GET", template, one.status_code, one.json())
    card = sent[4][1].json()
    assert [one.status_code for _, one in sent] == [200, 200, 200, 200, 200, 404]
    assert not {"not_verified", "research", "research_problem"} & set(card)
    assert any(not {"instance", "reads"} & set(one) for one in card["results"])


def test_a_body_missing_a_required_field_or_carrying_an_unnamed_one_fails() -> None:
    with pytest.raises(ValidationError, match="required"):
        check("POST", "/v1/conversations/{conversation_id}/messages", 202, {})
    with pytest.raises(ValidationError, match="title"):
        check("POST", "/v1/conversations/{conversation_id}/messages", 202, {"seq": 1, "title": ""})

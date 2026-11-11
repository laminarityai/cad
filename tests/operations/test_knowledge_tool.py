import pytest
from mcp import Client

from cad.server.app import build_server

pytestmark = pytest.mark.anyio


async def test_search_knowledge_returns_ranked_pointers_with_their_quotes() -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("search_knowledge", {"query": "PolyTerra PLA density"})
    assert not result.is_error
    assert result.structured_content is not None
    hits = result.structured_content["hits"]
    assert hits[0] == {
        "id": "kb:polymaker-polyterra-pla#density",
        "subject": "polymaker-polyterra-pla",
        "title": "PolyTerra PLA technical data sheet V6.0 (Polymaker)",
        "section": "Density",
        "page": "1",
        "url": "https://polymaker.com/wp-content/uploads/TDS_PolyTerra_PLA_V6.0_2026-06-08_EN.pdf",
        "retrieved": "2026-11-07",
        "text": hits[0]["text"],
    }
    assert '"1.31g/cm3 at 23°C"' in hits[0]["text"]
    assert "kb:polymaker-polyterra-pla-plus#density" in [hit["id"] for hit in hits]


async def test_search_knowledge_honors_k_and_returns_no_hits_when_nothing_matches() -> None:
    async with Client(build_server()) as client:
        one = await client.call_tool("search_knowledge", {"query": "density", "k": 1})
        none = await client.call_tool("search_knowledge", {"query": "quantum chromodynamics"})
    assert one.structured_content is not None
    assert len(one.structured_content["hits"]) == 1
    assert none.structured_content == {"hits": []}


@pytest.mark.parametrize("k", [0, 21])
async def test_search_knowledge_refuses_a_k_out_of_range(k: int) -> None:
    async with Client(build_server()) as client:
        result = await client.call_tool("search_knowledge", {"query": "density", "k": k})
    assert result.is_error

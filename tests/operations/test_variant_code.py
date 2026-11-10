import pytest

from tests.conftest import Session

pytestmark = pytest.mark.anyio


async def test_the_agent_reads_the_code_a_stored_variant_was_built_from(s: Session) -> None:
    code = "# a channel with a 2 mm side wall\nresult = None\n"
    vid = s.variant(code)
    assert await s.call("variant_code", variant_id=vid) == {"variant_id": vid, "code": code}


async def test_a_variant_that_is_not_stored_has_no_code(s: Session) -> None:
    text = await s.text("variant_code", variant_id="0" * 16)
    assert "no variant 0000000000000000 is stored" in text

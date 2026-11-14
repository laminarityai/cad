from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from cad.sandbox.image import BUILD, image_tag
from cad.variants import entry
from tests.support.auto_session import running

if TYPE_CHECKING:
    from tests.support.auto_session import Session

pytestmark = [pytest.mark.anyio, pytest.mark.docker]

COLOURED: Final = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text() + (
    "from build123d import Color, Compound, GeomType\n"
    "result.color = Color(0.85, 0.85, 0.8)\n"
    'areas = [Compound(result.faces().filter_by(GeomType.CYLINDER), label="holes", '
    "color=Color(0.2, 0.2, 0.2))]\n"
)


async def test_a_revision_under_auto_keeps_the_colours_and_areas_its_code_sets(s: Session) -> None:
    _, run_id = await running(s)
    done = await s.call("auto_revise", run_id=run_id, code=COLOURED)
    while done["settling"]:
        done = await s.call("auto_revise", run_id=run_id, code=COLOURED)
    vid = done["state"]["history"][-1]["variant_id"]
    held = entry.open_entry(s.tenant.variants, vid, image_tag(BUILD))
    kept = {area.name: area.colour for area in held.areas}
    assert kept == {"unnamed": "#d9d9cc", "holes": "#333333"}

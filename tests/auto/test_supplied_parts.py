"""A revision under an Auto run reads and places supplied parts as build_variant does
(ADR-0012), and the run counts it by the build it made, parts included."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.briefs import store as briefs
from cad.sandbox import builder, image
from cad.sandbox.builder import Run, Supplied
from cad.sandbox.outcome import BuildFailed
from cad.uploads import store
from cad.uploads.model import kind_of
from cad.variants import entry
from tests.support.auto_session import running
from tests.support.rows import RAIL, fake_ingest

if TYPE_CHECKING:
    from collections.abc import Sequence

    from tests.support.auto_session import Session

pytestmark = pytest.mark.anyio
CODE = "raise NameError('a plate around the wheel')"
SPOT = {"at": [30.0, 20.0, 0.0], "rotate": [0.0, 0.0, 0.0]}
PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")


async def test_a_revision_is_sent_its_parts_and_counted_by_the_build_it_made(
    s: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[Sequence[Supplied]] = []

    def build(
        code: str, image_id: str, *, wall_seconds: int, parts: Sequence[Supplied] = ()
    ) -> Run:
        sent.append(parts)
        return Run(BuildFailed(error="NameError", traceback=""), "")

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(image, "current_image", "sha256:{}".format)
    brief_id, run_id = await running(s)
    project = briefs.read_brief(s.roots, brief_id).project
    kind = kind_of("wheel.step")
    part = store.add_part(
        s.roots.projects, project, "wheel.step", kind, None, RAIL, PERSON, fake_ingest
    )
    asked = [{"part_id": part.record.id, "placements": [SPOT]}]
    await s.call("auto_revise", run_id=run_id, code=CODE, parts=asked)
    await s.call("auto_revise", run_id=run_id, code=CODE)
    [[wheel], plain] = sent
    assert (wheel.brep, plain) == (RAIL, ())
    [placed, alone] = s.run(run_id).state.history
    assert placed.code_sha256 == entry.build_sha256(CODE, (wheel.use,))
    assert alone.code_sha256 == entry.build_sha256(CODE)

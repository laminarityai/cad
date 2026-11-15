"""The card lists the parts the person supplied that the build read, from the signed build
record, and grades only the agent's body (ADR-0012). The checks are faked: no container runs."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cad.checks.lanes import Lanes
from cad.context_parts.ingest import Facts
from cad.context_parts.model import ContextPartRecord, FromUpload, StepRead
from cad.operations.brief_parts import named
from cad.projects.model import ProjectId
from cad.sandbox import image
from cad.sandbox.outcome import Build, Built, PartPlacement, PartUse
from cad.scorecard import score
from cad.scorecard.supplied import SuppliedPart, Uploaded
from cad.variants import entry
from tests.support.lanes import ran

TAG = "cad-sandbox:test"
CODE = "result = Box(100, 60, 5)\n"
PLATE = b"CASCADE Topology V3, a plate\n"
WHEEL_BREP = b"CASCADE Topology V3, a wheel\n"
WHEEL_SHA = hashlib.sha256(WHEEL_BREP).hexdigest()
PROJECT = ProjectId("p-0123456789abcdef")
CORNERS = tuple(PartPlacement(at=(x, y, 0.0), rotate=(90.0, 0.0, 0.0)) for x, y in [(1, 2), (3, 4)])
WHEEL = PartUse(
    part_id=f"part-{WHEEL_SHA[:16]}", project=PROJECT, brep_sha256=WHEEL_SHA, placements=CORNERS
)
RECORD = ContextPartRecord(
    project=PROJECT,
    name="wheel",
    source=FromUpload(
        file_name="wheel.step",
        file_sha256="f" * 64,
        read_as=StepRead(),
        account="user_alice",
        session_id="sess_1",
    ),
    brep_sha256=WHEEL_SHA,
    facts=Facts(solids=1, volume_mm3=1.0, box_min=(0, 0, 0), box_max=(1, 1, 1)),
    proposed_at=datetime(2026, 11, 14, tzinfo=UTC),
)


@pytest.fixture(autouse=True)
def tagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(image, "image_tag", {image.BUILD: TAG}.__getitem__)


def stored(root: Path, parts: tuple[PartUse, ...]) -> str:
    vid = entry.variant_id(CODE, TAG, parts)
    entry.save(root, vid, CODE, Build(outcome=Built(), output=""), PLATE, parts)
    return vid


def test_the_card_lists_each_supplied_part_as_the_signed_record_names_it(tmp_path: Path) -> None:
    vid = stored(tmp_path, (WHEEL,))
    card = score.score_variant(
        vid, "prusament-pla", tmp_path, lanes=Lanes(ran), parts={WHEEL.part_id: named(RECORD)}
    )
    assert card.supplied == (
        SuppliedPart(
            part_id=WHEEL.part_id,
            name="wheel",
            origin=Uploaded(file_name="wheel.step"),
            brep_sha256=WHEEL_SHA,
            placements=CORNERS,
        ),
    )
    assert card.brep_sha256 == hashlib.sha256(PLATE).hexdigest()
    shown = json.loads(card.model_dump_json())["supplied"][0]
    assert "user_alice" not in json.dumps(shown)
    peeked = score.peek_variant(
        vid, "prusament-pla", tmp_path, lanes=Lanes(ran), parts={WHEEL.part_id: named(RECORD)}
    )
    assert peeked.supplied == card.supplied


def test_a_card_with_no_supplied_parts_leaves_the_field_out(tmp_path: Path) -> None:
    card = score.score_variant(stored(tmp_path, ()), "prusament-pla", tmp_path, lanes=Lanes(ran))
    assert card.supplied == ()
    assert "supplied" not in json.loads(card.model_dump_json())

import hashlib
from pathlib import Path

import pytest
from chain import PlacedStep, Resolved, Unresolved
from supplied import Unsupplied

from cad.accounts.principal import AccountId, PersonSession
from cad.briefs import store as briefs
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built, PartPlacement, PartUse
from cad.scorecard.model import AwaitingConfirmation, Scorecard
from cad.scorecard.supplied import SuppliedPart, Uploaded
from cad.uploads import store as uploads
from cad.uploads.model import kind_of
from cad.variants import entry
from tests.support.cards import BREP, genuine_card, trace
from tests.support.rows import RAIL, fake_ingest

PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")
CODE = "result = Box(100, 60, 5)\n"
CORNERS = tuple(PartPlacement(at=(x, y, 0.0)) for x, y in [(-40, -25), (40, -25), (-40, 25)])


def supplied_card(roots: Roots, store: Path) -> Scorecard:
    """A card scored on a brief whose project holds an uploaded wheel, for a plate that placed it
    at three corners."""
    brief = briefs.create_brief(roots, "a plate with three wheels", new_project_id())
    kind = kind_of("wheel.step")
    part = uploads.add_part(
        roots.projects, brief.project, "wheel.step", kind, None, RAIL, PERSON, fake_ingest
    )
    use = PartUse(
        part_id=part.record.id,
        project=brief.project,
        brep_sha256=hashlib.sha256(RAIL).hexdigest(),
        placements=CORNERS,
    )
    vid = entry.variant_id(CODE, image_tag(BUILD), (use,))
    entry.save(store, vid, CODE, Build(outcome=Built(), output=""), BREP, (use,))
    row = SuppliedPart(
        part_id=use.part_id,
        name=part.record.name,
        origin=Uploaded(file_name="wheel.step"),
        brep_sha256=use.brep_sha256,
        placements=CORNERS,
    )
    return genuine_card(
        variant_id=vid, basis=AwaitingConfirmation(brief_id=brief.id), supplied=(row,)
    )


def doctored(card: Scorecard, **changes: object) -> Scorecard:
    return card.model_copy(update={"supplied": (card.supplied[0].model_copy(update=changes),)})


def test_a_card_whose_supplied_rows_match_the_signed_record_traces(
    roots: Roots, store: Path
) -> None:
    card = supplied_card(roots, store)
    traced = trace(card, store)
    assert [one for one in traced.failures if isinstance(one, Unsupplied)] == []
    placed = [one for one in traced.numbers if one.label.startswith("supplied")]
    assert len(placed) == 3 * 6
    step = PlacedStep(card.variant_id, card.supplied[0].part_id)
    assert {one.outcome for one in placed} == {Resolved((step,))}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"placements": CORNERS[:2]}, "is not the BREP and placements the signed build record"),
        ({"brep_sha256": "e" * 64}, "is not the BREP and placements the signed build record"),
        ({"name": "my own wheel"}, "name or origin"),
        ({"origin": Uploaded(file_name="tyre.step")}, "name or origin"),
    ],
)
def test_a_doctored_supplied_row_fails_the_card(
    roots: Roots, store: Path, changes: dict[str, object], reason: str
) -> None:
    traced = trace(doctored(supplied_card(roots, store), **changes), store)
    failures = [one.reason for one in traced.failures if isinstance(one, Unsupplied)]
    assert any(reason in one for one in failures), failures


def test_a_moved_copy_does_not_resolve(roots: Roots, store: Path) -> None:
    card = supplied_card(roots, store)
    moved = (PartPlacement(at=(-41, -25, 0.0)), *CORNERS[1:])
    traced = trace(doctored(card, placements=moved), store)
    at = next(one for one in traced.numbers if one.label == "supplied[0].placements[0].at[0]")
    assert at.outcome == Unresolved("the signed build record holds -40, not -41")


def test_a_card_that_leaves_out_a_part_the_build_read_fails(roots: Roots, store: Path) -> None:
    card = supplied_card(roots, store)
    part = card.supplied[0].part_id
    traced = trace(card.model_copy(update={"supplied": ()}), store)
    assert Unsupplied(f"the signed build record reads {part}, which the card leaves out") in (
        traced.failures
    )


def test_a_row_naming_a_part_the_project_does_not_hold_fails(roots: Roots, store: Path) -> None:
    card = supplied_card(roots, store)
    forged = "part-" + "0" * 16
    traced = trace(doctored(card, part_id=forged), store)
    reasons = [one.reason for one in traced.failures if isinstance(one, Unsupplied)]
    assert f"the card lists {forged}, which the signed build record of" in reasons[0]
    assert f"{forged} with BREP" in reasons[-1]

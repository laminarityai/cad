from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from cad.briefs import assumptions, store
from cad.briefs.assumptions import Assumption
from cad.briefs.model import BriefId, Target
from cad.projects.model import new_project_id
from cad.records.roots import Roots

TEXT = "A wall bracket for a shelf, under 150 g"
TARGET = TypeAdapter[Target](Target)
MASS = Assumption(
    target=TARGET.validate_python({"kind": "max_mass", "mass": {"magnitude": 120, "unit": "g"}}),
    why="a light part prints fast",
)
BOX = Assumption(
    target=TARGET.validate_python(
        {"kind": "envelope", "edges": [{"magnitude": 90, "unit": "mm"}] * 3}
    ),
    why="fits a desk drawer",
)
UNDER_150 = store.Draft(
    TARGET.validate_python({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}),
    "under 150 g",
)


def brief(roots: Roots) -> BriefId:
    return store.create_brief(roots, TEXT, new_project_id()).id


def assume(roots: Roots, brief_id: BriefId, *items: Assumption) -> assumptions.AssumptionSet | None:
    return assumptions.assume(roots, brief_id, items, set())


def slots(roots: Roots, brief_id: BriefId) -> list[str]:
    directory = roots.briefs / brief_id / assumptions.ASSUMPTIONS
    return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else []


def test_a_brief_nobody_assumed_for_has_no_assumptions(roots: Roots) -> None:
    assert assumptions.in_force(roots, brief(roots)) is None


def test_the_newest_set_is_the_one_in_force_and_earlier_sets_stay_stored(roots: Roots) -> None:
    brief_id = brief(roots)
    first = assume(roots, brief_id, MASS)
    second = assume(roots, brief_id, MASS, BOX)
    assert first is not None and second is not None
    assert (first.number, second.number) == (1, 2)
    assert assumptions.in_force(roots, brief_id) == second
    assert slots(roots, brief_id) == ["0001.signed", "0002.signed"]


def test_writing_the_set_in_force_again_stores_nothing(roots: Roots) -> None:
    brief_id = brief(roots)
    assume(roots, brief_id, MASS)
    again = assume(roots, brief_id, MASS)
    assert again is not None and again.number == 1
    assert slots(roots, brief_id) == ["0001.signed"]


def test_an_empty_set_clears_what_was_assumed_and_stores_nothing_when_nothing_was(
    roots: Roots,
) -> None:
    brief_id = brief(roots)
    assert assume(roots, brief_id) is None
    assert slots(roots, brief_id) == []
    assume(roots, brief_id, MASS)
    cleared = assume(roots, brief_id)
    assert cleared is not None and (cleared.number, cleared.assumptions) == (2, ())


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "made_of", "material": "prusament-pla"},
        {"kind": "closed_solid"},
        {"kind": "unchecked", "statement": "prints in PETG"},
    ],
)
def test_a_target_that_holds_no_number_is_not_an_assumption(
    roots: Roots, target: dict[str, Any]
) -> None:
    brief_id = brief(roots)
    held = Assumption(target=TARGET.validate_python(target), why="because")
    with pytest.raises(store.BadProposal, match=r"assumptions\[1\]"):
        assume(roots, brief_id, MASS, held)
    assert slots(roots, brief_id) == []


def test_a_clearance_assumption_names_a_context_part_of_the_project(roots: Roots) -> None:
    brief_id = brief(roots)
    clearance = Assumption(
        target=TARGET.validate_python(
            {
                "kind": "min_clearance",
                "part": "part-0123456789abcdef",
                "clearance": {"magnitude": 1, "unit": "mm"},
            }
        ),
        why="a snug fit",
    )
    with pytest.raises(store.BadProposal, match=r"assumptions\[0\].*not a context part"):
        assume(roots, brief_id, clearance)


def test_an_assumption_writes_no_proposal_and_changes_no_status(roots: Roots) -> None:
    brief_id = brief(roots)
    store.propose(roots, brief_id, [UNDER_150])
    before = store.read_state(roots, brief_id)
    assume(roots, brief_id, MASS, BOX)
    after = store.read_state(roots, brief_id)
    assert [(p.proposal.number, p.status, p.sha256) for p in after.proposals] == [
        (p.proposal.number, p.status, p.sha256) for p in before.proposals
    ]
    assert store.confirmed_requirements(roots, brief_id) is None


def test_a_record_the_store_did_not_sign_is_tampering(roots: Roots) -> None:
    brief_id = brief(roots)
    assume(roots, brief_id, MASS)
    [record] = (roots.briefs / brief_id / assumptions.ASSUMPTIONS).iterdir()
    record.write_bytes(record.read_bytes().replace(b"120", b"999"))
    with pytest.raises(store.TamperedBrief, match=brief_id):
        assumptions.in_force(roots, brief_id)
    with pytest.raises(store.TamperedBrief):
        assume(roots, brief_id, BOX)


def test_a_set_copied_between_briefs_is_tampering(roots: Roots, tmp_path: Path) -> None:
    first, second = brief(roots), brief(roots)
    assume(roots, first, MASS)
    assume(roots, second, BOX)
    directory = roots.briefs / second / assumptions.ASSUMPTIONS
    (directory / "0001.signed").write_bytes(
        (roots.briefs / first / assumptions.ASSUMPTIONS / "0001.signed").read_bytes()
    )
    with pytest.raises(store.TamperedBrief):
        assumptions.in_force(roots, second)

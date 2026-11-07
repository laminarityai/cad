import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from cad.briefs import store
from cad.briefs.model import Answer, BriefId, Confirmed, Decision, Declined, Target
from cad.briefs.store import Draft, Status

TEXT = "A wall bracket for a 2 kg shelf, under 150 g, printable in PETG"
TARGET = TypeAdapter[Target](Target)
UNDER_150 = Draft(
    TARGET.validate_python({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}),
    "under 150 g",
)
SHELF = Draft(
    TARGET.validate_python({"kind": "unchecked", "statement": "holds a 2 kg shelf"}),
    "for a 2 kg shelf",
)

type Tamper = Callable[[Path, BriefId, BriefId], None]


def decide(root: Path, brief_id: BriefId, number: int, answer: Answer) -> Decision:
    state = store.read_state(root, brief_id)
    proposed = state.proposal(number)
    assert proposed is not None
    decision = Decision(
        proposal=number,
        brief_sha256=state.brief_sha256,
        proposal_sha256=proposed.sha256,
        answer=answer,
        decided_at=datetime.now(UTC),
    )
    return store.record_decision(root, brief_id, decision)


def proposed(root: Path, *drafts: Draft) -> BriefId:
    brief = store.create_brief(root, TEXT)
    store.propose(root, brief.id, drafts)
    return brief.id


def statuses(root: Path, brief_id: str) -> list[Status]:
    return [p.status for p in store.read_state(root, brief_id).proposals]


def test_a_proposed_requirement_is_not_confirmed(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150, SHELF)
    assert statuses(tmp_path, brief_id) == [Status.PROPOSED]
    assert store.confirmed_requirements(tmp_path, brief_id) is None


def test_a_requirement_points_at_the_words_it_quotes(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150)
    state = store.read_state(tmp_path, brief_id)
    origin = state.proposals[0].proposal.requirements[0].origin
    assert state.brief.text[origin.start : origin.end] == "under 150 g"


def test_a_quote_not_in_the_brief_is_refused_naming_its_row(tmp_path: Path) -> None:
    brief = store.create_brief(tmp_path, TEXT)
    with pytest.raises(store.BadProposal, match=r"requirements\[1\]"):
        store.propose(tmp_path, brief.id, [UNDER_150, Draft(UNDER_150.target, "under 100 g")])
    assert statuses(tmp_path, brief.id) == []


def test_proposing_the_same_undecided_set_again_writes_nothing(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150, SHELF)
    again = store.propose(tmp_path, brief_id, [UNDER_150, SHELF])
    assert again.proposal.number == 1
    assert statuses(tmp_path, brief_id) == [Status.PROPOSED]


def test_a_person_confirms_a_whole_set(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150, SHELF)
    decide(tmp_path, brief_id, 1, Confirmed())
    confirmed = store.confirmed_requirements(tmp_path, brief_id)
    assert confirmed is not None
    assert confirmed.proposal == 1
    assert [r.target for r in confirmed.requirements] == [UNDER_150.target, SHELF.target]


def test_the_first_answer_stands(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150)
    decide(tmp_path, brief_id, 1, Declined(note="lighter please"))
    winner = decide(tmp_path, brief_id, 1, Confirmed())
    assert winner.answer == Declined(note="lighter please")
    assert statuses(tmp_path, brief_id) == [Status.DECLINED]


def test_a_newer_proposal_leaves_the_confirmed_set_in_force(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150, SHELF)
    decide(tmp_path, brief_id, 1, Confirmed())
    store.propose(tmp_path, brief_id, [SHELF])
    store.propose(tmp_path, brief_id, [UNDER_150])
    assert statuses(tmp_path, brief_id) == [Status.CONFIRMED, Status.SUPERSEDED, Status.PROPOSED]
    confirmed = store.confirmed_requirements(tmp_path, brief_id)
    assert confirmed is not None
    assert confirmed.proposal == 1


def test_a_confirmed_set_cannot_be_made_outside_the_store(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150)
    decide(tmp_path, brief_id, 1, Confirmed())
    confirmed = store.confirmed_requirements(tmp_path, brief_id)
    assert confirmed is not None
    with pytest.raises(TypeError):
        type(confirmed)(
            brief_id=confirmed.brief_id,
            proposal=2,
            decision_sha256="0" * 64,
            requirements=(),
            _seal=object(),  # pyright: ignore[reportArgumentType]
        )


def tamper_edit_byte(root: Path, brief_id: BriefId, other: BriefId) -> None:
    path = root / brief_id / "decisions" / "0001.signed"
    data = bytearray(path.read_bytes())
    data[-2] ^= 1
    path.write_bytes(bytes(data))


def tamper_flip_verdict(root: Path, brief_id: BriefId, other: BriefId) -> None:
    path = root / brief_id / "decisions" / "0001.signed"
    flipped = path.read_bytes().replace(
        b'"verdict":"declined","note":"no"', b'"verdict":"confirmed"'
    )
    assert flipped != path.read_bytes()
    path.write_bytes(flipped)


def tamper_move_slot(root: Path, brief_id: BriefId, other: BriefId) -> None:
    store.propose(root, brief_id, [SHELF])
    decisions = root / brief_id / "decisions"
    (decisions / "0001.signed").rename(decisions / "0002.signed")


def tamper_copy_from_other_brief(root: Path, brief_id: BriefId, other: BriefId) -> None:
    decide(root, other, 1, Confirmed())
    target = root / brief_id / "decisions" / "0001.signed"
    target.unlink()
    shutil.copy(root / other / "decisions" / "0001.signed", target)


def tamper_symlink(root: Path, brief_id: BriefId, other: BriefId) -> None:
    decide(root, other, 1, Confirmed())
    target = root / brief_id / "decisions" / "0001.signed"
    target.unlink()
    target.symlink_to(root / other / "decisions" / "0001.signed")


def tamper_status_field(root: Path, brief_id: BriefId, other: BriefId) -> None:
    (root / brief_id / "decisions" / "0001.signed").unlink(missing_ok=True)
    path = root / brief_id / "proposals" / "0001.signed"
    path.write_bytes(path.read_bytes().replace(b'{"brief_id"', b'{"status":"confirmed","brief_id"'))


def tamper_delete_proposal(root: Path, brief_id: BriefId, other: BriefId) -> None:
    (root / brief_id / "proposals" / "0001.signed").unlink()


@pytest.mark.parametrize(
    "tamper",
    [
        tamper_edit_byte,
        tamper_flip_verdict,
        tamper_move_slot,
        tamper_copy_from_other_brief,
        tamper_symlink,
        tamper_status_field,
        tamper_delete_proposal,
    ],
)
def test_a_tampered_brief_is_refused_and_confirms_nothing(tmp_path: Path, tamper: Tamper) -> None:
    brief_id = proposed(tmp_path, UNDER_150)
    other = proposed(tmp_path, UNDER_150)
    decide(tmp_path, brief_id, 1, Declined(note="no"))
    tamper(tmp_path, brief_id, other)
    with pytest.raises(store.TamperedBrief, match=f"brief {brief_id} .* operator must delete"):
        store.read_state(tmp_path, brief_id)
    with pytest.raises(store.TamperedBrief):
        store.confirmed_requirements(tmp_path, brief_id)


def test_a_refusal_names_the_brief_and_no_host_path(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path, UNDER_150)
    tamper_status_field(tmp_path, brief_id, brief_id)
    with pytest.raises(store.TamperedBrief) as refused:
        store.read_state(tmp_path, brief_id)
    assert str(tmp_path) not in str(refused.value)


@pytest.mark.parametrize("raw", ["../../etc", "0123456789ABCDEF", ""])
def test_a_malformed_brief_id_is_refused_before_any_path_is_built(tmp_path: Path, raw: str) -> None:
    with pytest.raises(store.UnknownBrief, match="16 lowercase hex"):
        store.read_state(tmp_path, raw)


def test_an_unknown_brief_is_refused(tmp_path: Path) -> None:
    with pytest.raises(store.UnknownBrief, match="no brief 0123456789abcdef"):
        store.read_state(tmp_path, "0123456789abcdef")


def test_an_unusable_key_is_reported_as_the_brief_store_key(tmp_path: Path) -> None:
    brief_id = proposed(tmp_path / "briefs", UNDER_150)
    (tmp_path / "briefs.key").chmod(0o644)
    with pytest.raises(store.BriefStoreUnusable, match="brief store's key is unusable"):
        store.read_state(tmp_path / "briefs", brief_id)

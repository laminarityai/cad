import hashlib
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from cad.briefs import store
from cad.briefs.model import Answer, BriefId, Confirmed, Decision, Declined, Target
from cad.briefs.store import Draft, Status
from cad.confirmations import answers
from cad.confirmations.answers import ItemAnswer, PageAnswer
from cad.projects.membership import project_briefs
from cad.projects.model import TamperedProject, new_project_id
from cad.records import signed
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable

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

type Tamper = Callable[[Roots, BriefId, BriefId], None]


def answer_on_page(roots: Roots, brief_id: BriefId, number: int, answer: Answer) -> bool:
    state = store.read_state(roots, brief_id)
    proposed = state.proposal(number)
    assert proposed is not None
    verdict = answer.verdict
    note = answer.note if isinstance(answer, Declined) else ""
    page = PageAnswer(
        project=state.brief.project,
        answers=(ItemAnswer(item=proposed.ref, verdict=verdict),),
        note=note,
        decided_at=datetime.now(UTC),
    )
    return answers.append_answer(roots.projects, state.brief.project, page)


def decide_before_pages(roots: Roots, brief_id: BriefId, number: int, answer: Answer) -> None:
    state = store.read_state(roots, brief_id)
    proposed = state.proposal(number)
    assert proposed is not None
    decision = Decision(
        proposal=number,
        brief_sha256=state.brief_sha256,
        proposal_sha256=proposed.sha256,
        answer=answer,
        decided_at=datetime.now(UTC),
    )
    path = roots.briefs / brief_id / store.DECISIONS / signed.slot_file(number)
    record = decision.model_dump_json().encode()
    assert signed.publish(
        signed.Store(roots.briefs, "brief"), f"{brief_id}/decision/{number}", path, record
    )


def proposed(roots: Roots, *drafts: Draft) -> BriefId:
    brief = store.create_brief(roots, TEXT, new_project_id())
    store.propose(roots, brief.id, drafts)
    return brief.id


def statuses(roots: Roots, brief_id: str) -> list[Status]:
    return [p.status for p in store.read_state(roots, brief_id).proposals]


def test_a_proposed_requirement_is_not_confirmed(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150, SHELF)
    assert statuses(roots, brief_id) == [Status.PROPOSED]
    assert store.confirmed_requirements(roots, brief_id) is None


def test_a_requirement_points_at_the_words_it_quotes(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    state = store.read_state(roots, brief_id)
    origin = state.proposals[0].proposal.requirements[0].origin
    assert state.brief.text[origin.start : origin.end] == "under 150 g"


def test_a_quote_not_in_the_brief_is_refused_naming_its_row(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id())
    with pytest.raises(store.BadProposal, match=r"requirements\[1\]"):
        store.propose(roots, brief.id, [UNDER_150, Draft(UNDER_150.target, "under 100 g")])
    assert statuses(roots, brief.id) == []


def test_proposing_the_same_undecided_set_again_writes_nothing(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150, SHELF)
    again = store.propose(roots, brief_id, [UNDER_150, SHELF])
    assert again.proposal.number == 1
    assert statuses(roots, brief_id) == [Status.PROPOSED]


def test_a_person_confirms_a_whole_set(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150, SHELF)
    answer_on_page(roots, brief_id, 1, Confirmed())
    confirmed = store.confirmed_requirements(roots, brief_id)
    assert confirmed is not None
    assert confirmed.proposal == 1
    assert [r.target for r in confirmed.requirements] == [UNDER_150.target, SHELF.target]


def test_the_first_answer_stands(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    assert answer_on_page(roots, brief_id, 1, Declined(note="lighter please"))
    assert not answer_on_page(roots, brief_id, 1, Confirmed())
    answered = store.read_state(roots, brief_id).proposals[0].answered
    assert answered is not None and answered.answer == Declined(note="lighter please")
    assert statuses(roots, brief_id) == [Status.DECLINED]


def test_a_decision_from_before_pages_wins_over_a_page_answer(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    answer_on_page(roots, brief_id, 1, Declined(note="no"))
    decide_before_pages(roots, brief_id, 1, Confirmed())
    confirmed = store.confirmed_requirements(roots, brief_id)
    decision = roots.briefs / brief_id / store.DECISIONS / "0001.signed"
    record = decision.read_bytes().partition(b"\n")[2]
    assert confirmed is not None
    assert confirmed.decision_sha256 == hashlib.sha256(record).hexdigest()


def test_a_page_answer_names_the_set_it_confirmed(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    answer_on_page(roots, brief_id, 1, Confirmed())
    project = store.read_brief(roots, brief_id).project
    [(sha256, _)] = answers.read_ledger(roots.projects, project).answers
    confirmed = store.confirmed_requirements(roots, brief_id)
    assert confirmed is not None and confirmed.decision_sha256 == sha256


def test_a_tampered_answer_refuses_the_brief_but_keeps_it_in_its_project(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    answer_on_page(roots, brief_id, 1, Confirmed())
    project = store.read_brief(roots, brief_id).project
    [path] = (roots.projects / project / "answers").iterdir()
    path.write_bytes(path.read_bytes().replace(b"confirmed", b"declined"))
    with pytest.raises(TamperedProject, match=f"project {project}") as refused:
        store.confirmed_requirements(roots, brief_id)
    assert str(roots.projects) not in str(refused.value)
    assert project_briefs(roots, project) == (brief_id,)


def test_a_newer_proposal_leaves_the_confirmed_set_in_force(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150, SHELF)
    answer_on_page(roots, brief_id, 1, Confirmed())
    store.propose(roots, brief_id, [SHELF])
    store.propose(roots, brief_id, [UNDER_150])
    assert statuses(roots, brief_id) == [Status.CONFIRMED, Status.SUPERSEDED, Status.PROPOSED]
    confirmed = store.confirmed_requirements(roots, brief_id)
    assert confirmed is not None
    assert confirmed.proposal == 1


def test_a_confirmed_set_cannot_be_made_outside_the_store(roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    answer_on_page(roots, brief_id, 1, Confirmed())
    confirmed = store.confirmed_requirements(roots, brief_id)
    assert confirmed is not None
    with pytest.raises(TypeError):
        type(confirmed)(
            brief_id=confirmed.brief_id,
            proposal=2,
            decision_sha256="0" * 64,
            requirements=(),
            _seal=object(),  # pyright: ignore[reportArgumentType]
        )


def tamper_edit_byte(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    path = roots.briefs / brief_id / "decisions" / "0001.signed"
    data = bytearray(path.read_bytes())
    data[-2] ^= 1
    path.write_bytes(bytes(data))


def tamper_flip_verdict(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    path = roots.briefs / brief_id / "decisions" / "0001.signed"
    flipped = path.read_bytes().replace(
        b'"verdict":"declined","note":"no"', b'"verdict":"confirmed"'
    )
    assert flipped != path.read_bytes()
    path.write_bytes(flipped)


def tamper_move_slot(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    store.propose(roots, brief_id, [SHELF])
    decisions = roots.briefs / brief_id / "decisions"
    (decisions / "0001.signed").rename(decisions / "0002.signed")


def tamper_copy_from_other_brief(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    decide_before_pages(roots, other, 1, Confirmed())
    target = roots.briefs / brief_id / "decisions" / "0001.signed"
    target.unlink()
    shutil.copy(roots.briefs / other / "decisions" / "0001.signed", target)


def tamper_symlink(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    decide_before_pages(roots, other, 1, Confirmed())
    target = roots.briefs / brief_id / "decisions" / "0001.signed"
    target.unlink()
    target.symlink_to(roots.briefs / other / "decisions" / "0001.signed")


def tamper_status_field(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    (roots.briefs / brief_id / "decisions" / "0001.signed").unlink(missing_ok=True)
    path = roots.briefs / brief_id / "proposals" / "0001.signed"
    path.write_bytes(path.read_bytes().replace(b'{"brief_id"', b'{"status":"confirmed","brief_id"'))


def tamper_delete_proposal(roots: Roots, brief_id: BriefId, other: BriefId) -> None:
    (roots.briefs / brief_id / "proposals" / "0001.signed").unlink()


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
def test_a_tampered_brief_is_refused_and_confirms_nothing(roots: Roots, tamper: Tamper) -> None:
    brief_id = proposed(roots, UNDER_150)
    other = proposed(roots, UNDER_150)
    decide_before_pages(roots, brief_id, 1, Declined(note="no"))
    tamper(roots, brief_id, other)
    with pytest.raises(store.TamperedBrief, match=f"brief {brief_id} .* operator must delete"):
        store.read_state(roots, brief_id)
    with pytest.raises(store.TamperedBrief):
        store.confirmed_requirements(roots, brief_id)


def test_a_refusal_names_the_brief_and_no_host_path(tmp_path: Path, roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    tamper_status_field(roots, brief_id, brief_id)
    with pytest.raises(store.TamperedBrief) as refused:
        store.read_state(roots, brief_id)
    assert str(tmp_path) not in str(refused.value)


@pytest.mark.parametrize("raw", ["../../etc", "0123456789ABCDEF", ""])
def test_a_malformed_brief_id_is_refused_before_any_path_is_built(roots: Roots, raw: str) -> None:
    with pytest.raises(store.UnknownBrief, match="16 lowercase hex"):
        store.read_state(roots, raw)


def test_an_unknown_brief_is_refused(roots: Roots) -> None:
    with pytest.raises(store.UnknownBrief, match="no brief 0123456789abcdef"):
        store.read_state(roots, "0123456789abcdef")


def test_an_unusable_key_is_reported_as_the_brief_store_key(tmp_path: Path, roots: Roots) -> None:
    brief_id = proposed(roots, UNDER_150)
    (tmp_path / "briefs.key").chmod(0o644)
    with pytest.raises(StoreUnusable, match="brief store's key is unusable"):
        store.read_state(roots, brief_id)

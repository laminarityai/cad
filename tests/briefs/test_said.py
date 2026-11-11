import shutil

import pytest
from pydantic import TypeAdapter

from cad.briefs import said, store
from cad.briefs.model import Target
from cad.briefs.store import Draft, Status
from cad.projects.model import new_project_id
from cad.records.roots import Roots

TEXT = "A wall hook under 150 g"
LATER = "it has to hold a 20 N bag"
TARGET = TypeAdapter[Target](Target)
UNDER_150 = Draft(
    TARGET.validate_python({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}),
    "under 150 g",
)
HOLDS_20_N = Draft(
    TARGET.validate_python({"kind": "unchecked", "statement": "holds 20 N"}), "hold a 20 N bag"
)
HEARD = said.Words(
    newest_first=(said.Spoken(7, LATER), said.Spoken(3, "an older message about a 20 N bag"))
)


def quoted(roots: Roots, brief_id: str, number: int) -> list[str]:
    state = store.read_state(roots, brief_id)
    found = state.proposal(number)
    assert found is not None
    return [state.brief.text[r.origin.start : r.origin.end] for r in found.requirements]


def test_a_quote_only_a_later_message_holds_adds_it_and_proposes_on_the_same_brief(
    roots: Roots,
) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id(), seq=1)
    store.propose(roots, brief.id, [UNDER_150])
    before = store.read_state(roots, brief.id).brief_sha256
    second = store.propose(roots, brief.id, [UNDER_150, HOLDS_20_N], HEARD)
    state = store.read_state(roots, brief.id)
    assert second.proposal.number == 2
    assert state.brief.text == f"{TEXT}\n\n{LATER}"
    assert state.brief_sha256 == before
    assert quoted(roots, brief.id, 1) == ["under 150 g"]
    assert quoted(roots, brief.id, 2) == ["under 150 g", "hold a 20 N bag"]


def test_a_retry_adds_the_message_once_and_proposes_nothing_new(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id(), seq=1)
    first = store.propose(roots, brief.id, [HOLDS_20_N], HEARD)
    again = store.propose(roots, brief.id, [HOLDS_20_N], HEARD)
    assert again.proposal.number == first.proposal.number == 1
    assert store.read_brief(roots, brief.id).text == f"{TEXT}\n\n{LATER}"


def test_words_from_an_outside_client_are_added_once(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id())
    outside = said.Words(newest_first=(said.Spoken(None, LATER),))
    store.propose(roots, brief.id, [HOLDS_20_N], outside)
    store.propose(roots, brief.id, [UNDER_150, HOLDS_20_N], outside)
    assert store.read_brief(roots, brief.id).text == f"{TEXT}\n\n{LATER}"
    assert [p.status for p in store.read_state(roots, brief.id).proposals] == [
        Status.SUPERSEDED,
        Status.PROPOSED,
    ]


def test_a_quote_no_message_holds_is_refused_with_the_fix_and_adds_nothing(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id(), seq=1)
    unsaid = Draft(UNDER_150.target, "under 90 g")
    hint = said.Words(newest_first=HEARD.newest_first, refusal_hint="quote the person's own words")
    with pytest.raises(store.BadProposal, match=r"requirements\[1\].*quote the person's own words"):
        store.propose(roots, brief.id, [HOLDS_20_N, unsaid], hint)
    assert store.read_state(roots, brief.id).proposals == ()


def test_a_brief_stored_before_said_reads_and_grows(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id())
    shutil.rmtree(roots.briefs / brief.id / said.SAID)
    store.propose(roots, brief.id, [UNDER_150])
    assert store.read_brief(roots, brief.id).text == TEXT
    store.propose(roots, brief.id, [UNDER_150, HOLDS_20_N], HEARD)
    assert quoted(roots, brief.id, 2) == ["under 150 g", "hold a 20 N bag"]


def test_a_tampered_said_record_refuses_the_brief(roots: Roots) -> None:
    brief = store.create_brief(roots, TEXT, new_project_id())
    store.propose(roots, brief.id, [HOLDS_20_N], HEARD)
    path = roots.briefs / brief.id / said.SAID / "0001.signed"
    path.write_bytes(path.read_bytes().replace(b"20 N", b"90 N"))
    with pytest.raises(store.TamperedBrief, match=f"brief {brief.id} .* operator must delete"):
        store.read_state(roots, brief.id)

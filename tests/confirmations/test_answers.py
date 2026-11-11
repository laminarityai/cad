import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cad.confirmations import answers
from cad.confirmations.answers import ItemAnswer, ItemRef, PageAnswer
from cad.projects.model import ProjectBusy, ProjectId, TamperedProject
from cad.records import key, signed

PROJECT = ProjectId("p-0123456789abcdef")
OTHER = ProjectId("p-fedcba9876543210")
FIRST = ItemRef(kind="requirements", slot="0123456789abcdef/proposal/1", sha256="a" * 64)
SECOND = ItemRef(kind="requirements", slot="1111111111111111/proposal/1", sha256="b" * 64)


def page(project: ProjectId, *items: tuple[ItemRef, str], note: str = "") -> PageAnswer:
    return PageAnswer(
        project=project,
        answers=tuple(
            ItemAnswer(item=item, verdict="confirmed" if verdict == "c" else "declined")
            for item, verdict in items
        ),
        note=note,
        decided_at=datetime.now(UTC),
    )


def answer_file(root: Path, project: ProjectId = PROJECT, number: int = 1) -> Path:
    return root / project / answers.ANSWERS / signed.slot_file(number)


def test_a_project_nobody_answered_has_an_empty_ledger_and_no_key(tmp_path: Path) -> None:
    assert answers.read_ledger(tmp_path / "projects", PROJECT).of(FIRST) is None
    assert not key.key_path(tmp_path / "projects").exists()


def test_the_first_answer_listing_an_item_wins(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    assert answers.append_answer(root, PROJECT, page(PROJECT, (FIRST, "d"), note="lighter"))
    assert not answers.append_answer(root, PROJECT, page(PROJECT, (FIRST, "c"), (SECOND, "c")))
    assert answers.append_answer(root, PROJECT, page(PROJECT, (SECOND, "c")))
    ledger = answers.read_ledger(root, PROJECT)
    first, second = ledger.of(FIRST), ledger.of(SECOND)
    assert first is not None and second is not None
    assert (first.item.verdict, first.page.note) == ("declined", "lighter")
    assert second.sha256 == ledger.answers[1][0] != first.sha256
    assert sorted(p.name for p in answer_file(root).parent.iterdir()) == [
        "0001.signed",
        "0002.signed",
    ]


def test_an_answer_for_another_project_is_not_stored(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot go in"):
        answers.append_answer(tmp_path, PROJECT, page(OTHER, (FIRST, "c")))


def test_a_page_lists_each_item_once() -> None:
    with pytest.raises(ValueError, match="each item once"):
        page(PROJECT, (FIRST, "c"), (FIRST, "d"))


def edit_byte(root: Path) -> None:
    path = answer_file(root)
    data = bytearray(path.read_bytes())
    data[-2] ^= 1
    path.write_bytes(bytes(data))


def copy_from_other_project(root: Path) -> None:
    answers.append_answer(root, OTHER, page(OTHER, (SECOND, "c")))
    shutil.copy(answer_file(root, OTHER), answer_file(root))


def leave_a_gap(root: Path) -> None:
    answer_file(root).rename(answer_file(root, number=2))


def drop_the_key(root: Path) -> None:
    key.key_path(root).unlink()


@pytest.mark.parametrize("tamper", [edit_byte, copy_from_other_project, leave_a_gap, drop_the_key])
def test_a_tampered_answer_refuses_the_project_without_a_host_path(
    tmp_path: Path, tamper: Callable[[Path], None]
) -> None:
    root = tmp_path / "projects"
    answers.append_answer(root, PROJECT, page(PROJECT, (FIRST, "d")))
    tamper(root)
    for attempt in (
        lambda: answers.read_ledger(root, PROJECT),
        lambda: answers.append_answer(root, PROJECT, page(PROJECT, (SECOND, "c"))),
    ):
        with pytest.raises(TamperedProject, match=f"project {PROJECT} .* operator") as refused:
            attempt()
        assert str(tmp_path) not in str(refused.value)


def test_a_missing_key_is_never_minted_for_stored_answers(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    answers.append_answer(root, PROJECT, page(PROJECT, (FIRST, "d")))
    drop_the_key(root)
    with pytest.raises(TamperedProject):
        answers.read_ledger(root, PROJECT)
    assert not key.key_path(root).exists()


def test_a_slot_lost_on_every_attempt_is_busy_without_a_host_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def lost(*_: object) -> bool:
        return False

    monkeypatch.setattr(signed, "publish", lost)
    with pytest.raises(ProjectBusy, match=f"project {PROJECT} is being answered") as refused:
        answers.append_answer(tmp_path, PROJECT, page(PROJECT, (FIRST, "c")))
    assert str(tmp_path) not in str(refused.value)

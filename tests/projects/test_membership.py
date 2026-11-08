import shutil
from pathlib import Path

import pytest

from cad.briefs import store
from cad.briefs.model import BriefId
from cad.projects.membership import project_briefs, project_for_new_brief
from cad.projects.model import ProjectId, UnknownProject, new_project_id

TEXT = "A wall bracket for a 2 kg shelf, under 150 g"


def created(root: Path, project: str | None = None) -> tuple[BriefId, ProjectId]:
    chosen = project_for_new_brief(root, project)
    return store.create_brief(root, TEXT, chosen).id, chosen


def test_a_brief_is_born_in_one_project(tmp_path: Path) -> None:
    first, project = created(tmp_path)
    second, joined = created(tmp_path, project)
    other, elsewhere = created(tmp_path)
    assert joined == project != elsewhere
    assert project.startswith("p-")
    assert [store.project_of(tmp_path, b) for b in (first, second, other)] == [
        project,
        project,
        elsewhere,
    ]
    assert project_briefs(tmp_path, project) == (first, second)
    assert project_briefs(tmp_path, elsewhere) == (other,)


def test_a_crash_before_the_rename_leaves_nothing_the_project_counts(tmp_path: Path) -> None:
    first, project = created(tmp_path)
    shutil.copytree(tmp_path / first, tmp_path / ".incoming-0123456789abcdef")
    assert project_briefs(tmp_path, project) == (first,)


def test_a_brief_stored_before_projects_belongs_to_its_own_legacy_project(
    tmp_path: Path,
) -> None:
    legacy, _ = created(tmp_path)
    (tmp_path / legacy / store.PROJECT).unlink()
    assert store.project_of(tmp_path, legacy) == f"pb-{legacy}"
    assert project_briefs(tmp_path, store.project_of(tmp_path, legacy)) == (legacy,)
    assert store.read_state(tmp_path, legacy).brief.text == TEXT
    with pytest.raises(UnknownProject, match="before projects existed"):
        project_for_new_brief(tmp_path, f"pb-{legacy}")


def test_a_project_that_holds_no_brief_is_refused(tmp_path: Path) -> None:
    created(tmp_path)
    with pytest.raises(UnknownProject, match="no project p-"):
        project_for_new_brief(tmp_path, new_project_id())
    with pytest.raises(UnknownProject, match="16 lowercase hex"):
        project_for_new_brief(tmp_path, "../briefs")


def test_a_membership_copied_from_another_brief_is_tampered(tmp_path: Path) -> None:
    first, _ = created(tmp_path)
    second, other = created(tmp_path)
    shutil.copy(tmp_path / second / store.PROJECT, tmp_path / first / store.PROJECT)
    with pytest.raises(store.TamperedBrief):
        store.project_of(tmp_path, first)
    assert project_briefs(tmp_path, other) == (second,)

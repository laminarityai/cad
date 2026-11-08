import shutil
from pathlib import Path

import pytest

from cad.briefs import store
from cad.briefs.model import BriefId
from cad.projects.membership import project_briefs, project_for_new_brief
from cad.projects.model import NewProjectId, UnknownProject, new_project_id

TEXT = "A wall bracket for a 2 kg shelf, under 150 g"
LEGACY_STORE = Path(__file__).parents[1] / "records" / "legacy"
LEGACY_ID = BriefId("8482796846afca28")


def created(root: Path, project: str | None = None) -> tuple[BriefId, NewProjectId]:
    chosen = project_for_new_brief(root, project)
    return store.create_brief(root, TEXT, chosen).id, chosen


def stored_before_projects(tmp_path: Path) -> Path:
    """A brief store the pre-project code wrote, committed under tests/records/legacy."""
    shutil.copytree(LEGACY_STORE, tmp_path / "legacy")
    (tmp_path / "legacy" / "briefs.key").chmod(0o600)
    return tmp_path / "legacy" / "briefs"


def rewrite_brief_record(root: Path, brief_id: BriefId, edit: str, to: str) -> None:
    path = root / brief_id / store.BRIEF
    mac, _, record = path.read_bytes().partition(b"\n")
    assert edit.encode() in record
    path.write_bytes(mac + b"\n" + record.replace(edit.encode(), to.encode()))


def test_a_brief_is_born_in_one_project(tmp_path: Path) -> None:
    first, project = created(tmp_path)
    second, joined = created(tmp_path, project)
    other, elsewhere = created(tmp_path)
    assert joined == project != elsewhere
    assert project.startswith("p-")
    assert [store.read_state(tmp_path, b).brief.project for b in (first, second, other)] == [
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
    root = stored_before_projects(tmp_path)
    assert b"project_id" not in (root / LEGACY_ID / store.BRIEF).read_bytes()
    state = store.read_state(root, LEGACY_ID)
    assert (state.brief.project, state.confirmed is not None) == (f"pb-{LEGACY_ID}", True)
    assert project_briefs(root, state.brief.project) == (LEGACY_ID,)
    with pytest.raises(UnknownProject, match="before projects existed"):
        project_for_new_brief(root, f"pb-{LEGACY_ID}")


def test_a_project_that_holds_no_brief_is_refused(tmp_path: Path) -> None:
    created(tmp_path)
    with pytest.raises(UnknownProject, match="no project p-"):
        project_for_new_brief(tmp_path, new_project_id())
    with pytest.raises(UnknownProject, match="16 lowercase hex"):
        project_for_new_brief(tmp_path, "../briefs")


def test_moving_a_brief_to_another_project_breaks_its_signature(tmp_path: Path) -> None:
    first, project = created(tmp_path)
    second, other = created(tmp_path)
    rewrite_brief_record(tmp_path, first, project, other)
    with pytest.raises(store.TamperedBrief):
        store.read_state(tmp_path, first)
    assert project_briefs(tmp_path, other) == (second,)


def test_dropping_the_project_id_breaks_the_signature(tmp_path: Path) -> None:
    first, project = created(tmp_path)
    rewrite_brief_record(tmp_path, first, f',"project_id":"{project}"', "")
    with pytest.raises(store.TamperedBrief):
        store.read_state(tmp_path, first)
    assert project_briefs(tmp_path, project) == ()

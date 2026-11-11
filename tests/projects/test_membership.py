import shutil
from pathlib import Path

import pytest

from cad.briefs import store
from cad.briefs.model import BriefId
from cad.projects.membership import project_briefs, project_for_new_brief
from cad.projects.model import NewProjectId, UnknownProject, new_project_id
from cad.records.roots import Roots

TEXT = "A wall bracket for a 2 kg shelf, under 150 g"
LEGACY_STORE = Path(__file__).parents[1] / "records" / "legacy"
LEGACY_ID = BriefId("8482796846afca28")


def created(roots: Roots, project: str | None = None) -> tuple[BriefId, NewProjectId]:
    chosen = project_for_new_brief(roots, project)
    return store.create_brief(roots, TEXT, chosen).id, chosen


def stored_before_projects(tmp_path: Path) -> Roots:
    """A brief store the pre-project code wrote, committed under tests/records/legacy."""
    shutil.copytree(LEGACY_STORE, tmp_path / "legacy")
    (tmp_path / "legacy" / "briefs.key").chmod(0o600)
    return Roots(tmp_path / "legacy" / "briefs", tmp_path / "legacy" / "projects")


def rewrite_brief_record(roots: Roots, brief_id: BriefId, edit: str, to: str) -> None:
    path = roots.briefs / brief_id / store.BRIEF
    mac, _, record = path.read_bytes().partition(b"\n")
    assert edit.encode() in record
    path.write_bytes(mac + b"\n" + record.replace(edit.encode(), to.encode()))


def test_a_brief_is_born_in_one_project(roots: Roots) -> None:
    first, project = created(roots)
    second, joined = created(roots, project)
    other, elsewhere = created(roots)
    assert joined == project != elsewhere
    assert project.startswith("p-")
    assert [store.read_state(roots, b).brief.project for b in (first, second, other)] == [
        project,
        project,
        elsewhere,
    ]
    assert project_briefs(roots, project) == (first, second)
    assert project_briefs(roots, elsewhere) == (other,)


def test_a_crash_before_the_rename_leaves_nothing_the_project_counts(roots: Roots) -> None:
    first, project = created(roots)
    shutil.copytree(roots.briefs / first, roots.briefs / ".incoming-0123456789abcdef")
    assert project_briefs(roots, project) == (first,)


def test_a_brief_stored_before_projects_belongs_to_its_own_legacy_project(
    tmp_path: Path,
) -> None:
    roots = stored_before_projects(tmp_path)
    assert b"project_id" not in (roots.briefs / LEGACY_ID / store.BRIEF).read_bytes()
    state = store.read_state(roots, LEGACY_ID)
    assert (state.brief.project, state.confirmed is not None) == (f"pb-{LEGACY_ID}", True)
    assert project_briefs(roots, state.brief.project) == (LEGACY_ID,)
    with pytest.raises(UnknownProject, match="before projects existed"):
        project_for_new_brief(roots, f"pb-{LEGACY_ID}")


def test_a_project_that_holds_no_brief_is_refused(roots: Roots) -> None:
    created(roots)
    with pytest.raises(UnknownProject, match="no project p-"):
        project_for_new_brief(roots, new_project_id())
    with pytest.raises(UnknownProject, match="16 lowercase hex"):
        project_for_new_brief(roots, "../briefs")


def test_moving_a_brief_to_another_project_breaks_its_signature(roots: Roots) -> None:
    first, project = created(roots)
    second, other = created(roots)
    rewrite_brief_record(roots, first, project, other)
    with pytest.raises(store.TamperedBrief):
        store.read_state(roots, first)
    assert project_briefs(roots, other) == (second,)


def test_dropping_the_project_id_breaks_the_signature(roots: Roots) -> None:
    first, project = created(roots)
    rewrite_brief_record(roots, first, f',"project_id":"{project}"', "")
    with pytest.raises(store.TamperedBrief):
        store.read_state(roots, first)
    assert project_briefs(roots, project) == ()

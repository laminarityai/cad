from pathlib import Path

import pytest

from cad.briefs.model import BriefId
from cad.checks.jobs import JobResult, JobSpec
from cad.checks.lanes import Lanes
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.sandbox.bodies import Bodies
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.variant_sets import store
from cad.variant_sets.model import Chosen, Joined, Revision, SetKey
from cad.variants import entry

KEY = SetKey(ProjectId("p-" + "1" * 16), BriefId("2" * 16))


def unrun(job: JobSpec) -> JobResult:
    raise AssertionError(f"no check runs here: {job.key}")


def no_choice(previous: Revision | None, bodies: Bodies | None) -> Chosen:
    return Chosen()


def this_set(roots: Roots, brief_id: str) -> SetKey:
    return KEY


def stored(variants: Path, code: str) -> None:
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(variants, vid, code, Build(outcome=Built(), output=""), b"brep " + code.encode())


@pytest.mark.parametrize("error", [StoreUnusable("a set file is unreadable"), OSError("EIO")])
def test_a_revision_built_while_another_set_cannot_be_read_still_joins_its_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    roots, variants = Roots(tmp_path / "briefs", tmp_path / "projects"), tmp_path / "variants"
    monkeypatch.setattr(store, "set_key", this_set)
    for code in ("result = 'first'", "result = 'second'"):
        stored(variants, code)

    def build(code: str) -> Joined:
        joined = store.build_into_set(
            roots, variants, KEY.brief_id, code, 1, no_choice, lanes=Lanes(unrun)
        ).variant_set
        assert isinstance(joined, Joined)
        return joined

    build("result = 'first'")

    def unreadable(root: Path) -> object:
        raise error

    monkeypatch.setattr(store, "account_slots", unreadable)
    assert build("result = 'second'").revision == 2

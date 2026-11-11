from pathlib import Path

from cad.geometry.store import GEOMETRY_ROOT
from cad.records.roots import BRIEFS_ROOT, DATA_ROOT, HOME_ROOTS, PROJECTS_ROOT
from cad.sandbox.stage import STAGE_ROOT
from cad.variants.entry import VARIANTS_ROOT


def test_every_store_lives_under_the_cad_directory_in_home() -> None:
    roots = (DATA_ROOT, BRIEFS_ROOT, PROJECTS_ROOT, VARIANTS_ROOT, STAGE_ROOT, GEOMETRY_ROOT)
    cad = Path.home() / ".cad"
    names = ("briefs", "projects", "variants", "stage", "geometry")
    assert roots == (cad, *(cad / name for name in names))
    assert (HOME_ROOTS.briefs, HOME_ROOTS.projects) == (BRIEFS_ROOT, PROJECTS_ROOT)

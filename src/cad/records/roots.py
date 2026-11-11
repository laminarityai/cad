from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.data_root import DATA_ROOT
from cad.records import signed

BRIEFS_ROOT: Final = DATA_ROOT / "briefs"
PROJECTS_ROOT: Final = DATA_ROOT / "projects"
PROJECT_STORE_NAME: Final = "project"


@dataclass(frozen=True, slots=True)
class Roots:
    briefs: Path
    projects: Path


HOME_ROOTS: Final = Roots(BRIEFS_ROOT, PROJECTS_ROOT)


def project_store(root: Path) -> signed.Store:
    return signed.Store(root, PROJECT_STORE_NAME)

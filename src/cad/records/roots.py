from pathlib import Path
from typing import Final

from cad.records import signed

PROJECTS_ROOT: Final = Path.home() / ".cad" / "projects"
PROJECT_STORE_NAME: Final = "project"


def project_store(root: Path) -> signed.Store:
    return signed.Store(root, PROJECT_STORE_NAME)

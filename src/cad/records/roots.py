from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True, slots=True)
class Roots:
    briefs: Path
    projects: Path


HOME_ROOTS: Final = Roots(Path.home() / ".cad" / "briefs", Path.home() / ".cad" / "projects")

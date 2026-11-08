from dataclasses import dataclass
from pathlib import Path
from typing import Final


@dataclass(frozen=True, slots=True)
class Roots:
    """The two signed stores a confirmation reads: briefs and their proposals, and projects with
    the person's answers. Each has its own key beside it, `<root>.key`."""

    briefs: Path
    projects: Path


HOME_ROOTS: Final = Roots(Path.home() / ".cad" / "briefs", Path.home() / ".cad" / "projects")

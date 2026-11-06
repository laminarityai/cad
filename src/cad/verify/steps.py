import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON = sys.executable
ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    argv: tuple[str, ...]
    show_output: bool = False


STEPS: tuple[Step, ...] = (
    Step("basedpyright", (PYTHON, "-m", "basedpyright")),
    Step("basedpyright skills", (PYTHON, "-m", "basedpyright", "-p", ".claude/pyrightconfig.json")),
    Step("ruff check", (PYTHON, "-m", "ruff", "check")),
    Step("ruff format", (PYTHON, "-m", "ruff", "format", "--check")),
    Step("file size", (PYTHON, str(ROOT / "tools" / "check_file_size.py"))),
    Step("pytest", (PYTHON, "-m", "pytest", "-q")),
    Step("app", (PYTHON, "-m", "cad.server.probe"), show_output=True),
)

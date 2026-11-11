import sys
from dataclasses import dataclass
from pathlib import Path

PYTHON = sys.executable
ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / ".claude" / "skills" / "protocol-models"


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    argv: tuple[str, ...]
    show_output: bool = False


STEPS: tuple[Step, ...] = (
    # -p names the config: searching upward from a worktree under .claude/ finds
    # .claude/pyrightconfig.json first, which checks only the skills.
    Step("basedpyright", (PYTHON, "-m", "basedpyright", "-p", "pyproject.toml")),
    Step("basedpyright skills", (PYTHON, "-m", "basedpyright", "-p", ".claude/pyrightconfig.json")),
    Step("ruff check", (PYTHON, "-m", "ruff", "check")),
    Step("ruff format", (PYTHON, "-m", "ruff", "format", "--check")),
    Step("file size", (PYTHON, str(ROOT / "tools" / "check_file_size.py"))),
    Step("materials table", (PYTHON, "-m", "cad.tables.validate")),
    Step("api types", (PYTHON, str(ROOT / "tools" / "gen_ts.py"), "--check")),
    Step("web lint", (PYTHON, str(ROOT / "tools" / "web.py"), "lint")),
    Step("web test", (PYTHON, str(ROOT / "tools" / "web.py"), "test")),
    Step("web build", (PYTHON, str(ROOT / "tools" / "web.py"), "build")),
    Step("protocol models", (PYTHON, str(MODELS / "scripts" / "check_models.py"))),
    Step("sandbox image", (PYTHON, "-m", "cad.sandbox", "build-image")),
    Step(
        "pytest",
        (PYTHON, "-m", "pytest", "-q", "-n", "4", "--dist", "loadfile", "--durations=0"),
        show_output=True,
    ),
    Step("app", (PYTHON, "-m", "cad.server.probe"), show_output=True),
)

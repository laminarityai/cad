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
    # A slow step runs in CI on every PR and locally only under --all or --only.
    slow: bool = False
    # Patterns, fnmatch style and relative to the checkout, for every file the step's result
    # depends on: the files it reads, its tools' config and the lockfile. A `*` matches `/` too.
    # A fast step that passed is skipped until one of them changes; with none it always runs.
    # Declare them wide: a stamp that hides a failure is worse than no stamp.
    inputs: tuple[str, ...] = ()
    # Executables on PATH whose resolved location is part of the stamp, so an upgrade reruns.
    tools: tuple[str, ...] = ()
    # Files the step makes that something else serves. A step is skipped only while they exist.
    outputs: tuple[str, ...] = ()


# Every Python file and what decides how it is checked: the config, the interpreter, the packages.
PYTHON_INPUTS = ("*.py", "*.pyi", "pyproject.toml", "uv.lock", ".python-version")
# The web steps read nothing outside web/ but the two scripts that run them.
WEB_INPUTS = ("web/*", "tools/web.py", "tools/gen_ts.py", "uv.lock", ".python-version")
NODE = ("node", "npm")
API_WEB = ("web/package.json", "web/package-lock.json", "web/src/api/*")


STEPS: tuple[Step, ...] = (
    # -p names the config: searching upward from a worktree under .claude/ finds
    # .claude/pyrightconfig.json first, which checks only the skills.
    Step(
        "basedpyright",
        (PYTHON, "-m", "basedpyright", "-p", "pyproject.toml"),
        inputs=PYTHON_INPUTS,
    ),
    Step(
        "basedpyright skills",
        (PYTHON, "-m", "basedpyright", "-p", ".claude/pyrightconfig.json"),
        inputs=(*PYTHON_INPUTS, ".claude/*"),
    ),
    Step("ruff check", (PYTHON, "-m", "ruff", "check")),
    Step("ruff format", (PYTHON, "-m", "ruff", "format", "--check")),
    Step("file size", (PYTHON, str(ROOT / "tools" / "check_file_size.py"))),
    # The layers contract in pyproject.toml. import-linter ships a script, not a -m entry point.
    Step("layers", (str(Path(PYTHON).with_name("lint-imports")), "--no-cache", "--no-logo")),
    Step("materials table", (PYTHON, "-m", "cad.tables.validate")),
    # The OpenAPI document is built by importing the routes, which can read the tables.
    Step(
        "api types",
        (PYTHON, str(ROOT / "tools" / "gen_ts.py"), "--check"),
        inputs=(*PYTHON_INPUTS, "tables/*", "knowledge/*", "sandbox/*", *API_WEB),
        tools=NODE,
    ),
    Step(
        "web lint", (PYTHON, str(ROOT / "tools" / "web.py"), "lint"), inputs=WEB_INPUTS, tools=NODE
    ),
    Step(
        "web test", (PYTHON, str(ROOT / "tools" / "web.py"), "test"), inputs=WEB_INPUTS, tools=NODE
    ),
    # The app serves web/dist, and a missing build says to run verify, so verify must make it.
    Step(
        "web build",
        (PYTHON, str(ROOT / "tools" / "web.py"), "build"),
        inputs=WEB_INPUTS,
        tools=NODE,
        outputs=("web/dist/index.html",),
    ),
    Step("protocol models", (PYTHON, str(MODELS / "scripts" / "check_models.py")), slow=True),
    Step("sandbox image", (PYTHON, "-m", "cad.sandbox", "build-image"), slow=True),
    Step("pytest", (PYTHON, "-m", "pytest", "-q", "-n", "4", "--dist", "loadfile"), slow=True),
    Step("app", (PYTHON, "-m", "cad.server.probe"), show_output=True, slow=True),
)

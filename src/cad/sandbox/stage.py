import ast
import hashlib
import importlib.metadata
import secrets
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from cad.sandbox.container import ReadOnlyMount

SANDBOX_DIR: Final = Path(__file__).parent
SRC_ROOT: Final = Path(__file__).parents[2]
CONTAINER_ENTRY: Final = "cad.checks.container.runner"
PACKAGE_PATH: Final = "cad/checks/container"
STAGE_ROOT: Final = Path.home() / ".cad" / "stage"
DIGEST_CHARS: Final = 16
TARGET: Final = "/opt/trusted"
BOOT: Final = (
    f"import sys; sys.path.insert(0, {TARGET!r}); from {CONTAINER_ENTRY} import main; main()"
)


@dataclass(frozen=True, slots=True)
class Sources:
    files: Mapping[str, bytes]
    digest: str
    packages: Mapping[str, str]


def read_sources(*entries: str, root: Path = SRC_ROOT) -> Sources:
    found: dict[str, bytes] = {}
    libraries: set[str] = set()
    pending = [
        path for entry in entries for path in _files_run_by_importing(entry, root, required=True)
    ]
    while pending:
        path = pending.pop()
        name = path.relative_to(root).as_posix()
        if name not in found:
            found[name] = path.read_bytes()
            imports = _imports(path)
            pending += (
                file for module in imports for file in _files_run_by_importing(module, root)
            )
            libraries |= {
                top
                for top in (module.split(".")[0] for module in imports)
                if top not in sys.stdlib_module_names and not _files_run_by_importing(top, root)
            }
    files = dict(sorted(found.items()))
    digest = hashlib.sha256()
    for path, data in files.items():
        digest.update(f"{path}\0".encode())
        digest.update(hashlib.sha256(data).digest())
    return Sources(files, digest.hexdigest(), _installed(libraries))


def _installed(libraries: set[str]) -> dict[str, str]:
    owners = importlib.metadata.packages_distributions()
    pending = [owner for library in libraries for owner in owners[library]]
    versions: dict[str, str] = {}
    while pending:
        distribution = importlib.metadata.distribution(pending.pop())
        name = canonicalize_name(distribution.name)
        if name not in versions:
            versions[name] = distribution.version
            requirements = map(Requirement, distribution.requires or ())
            pending += (
                required.name
                for required in requirements
                if required.marker is None or required.marker.evaluate({"extra": ""})
            )
    return dict(sorted(versions.items()))


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_bytes(), str(path))):
        if isinstance(node, ast.Import):
            modules |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise ValueError(f"{path} has a relative import, which read_sources cannot follow")
            modules |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    return modules


def _files_run_by_importing(module: str, root: Path, *, required: bool = False) -> list[Path]:
    parts = module.split(".")
    files: list[Path] = []
    for depth in range(1, len(parts) + 1):
        base = root.joinpath(*parts[:depth])
        if (base / "__init__.py").is_file():
            files.append(base / "__init__.py")
        elif base.with_suffix(".py").is_file():
            files.append(base.with_suffix(".py"))
        elif not base.is_dir():
            if required:
                raise ModuleNotFoundError(f"no module {module} under {root}")
            break
    return files


def materialize(sources: Sources, root: Path = STAGE_ROOT) -> Path:
    target = root / sources.digest[:DIGEST_CHARS]
    if _holds(target, sources):
        return target
    root.mkdir(parents=True, exist_ok=True)
    building = root / f".building-{secrets.token_hex(8)}"
    try:
        for path, data in sources.files.items():
            staged = building / path
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data)
            staged.chmod(0o444)
        for directory in sorted((p for p in building.rglob("*") if p.is_dir()), reverse=True):
            directory.chmod(0o555)
        # Rename before discarding anything: another process may have staged the target and be
        # mounting it, and the rename fails only when something is already there.
        try:
            building.rename(target)  # macOS refuses to rename a directory it cannot write
        except OSError:
            if _holds(target, sources):
                return target
            _discard(target)
            building.rename(target)
        target.chmod(0o555)
    finally:
        _discard(building)
    return target


def check_mount(sources: Sources | None = None) -> ReadOnlyMount:
    return ReadOnlyMount(materialize(SOURCES if sources is None else sources, STAGE_ROOT), TARGET)


def _holds(directory: Path, sources: Sources) -> bool:
    if not directory.is_dir() or directory.is_symlink():
        return False
    present = {
        path.relative_to(directory).as_posix(): path
        for path in directory.rglob("*")
        if path.is_file()
    }
    return present.keys() == sources.files.keys() and all(
        not path.is_symlink() and path.read_bytes() == sources.files[name]
        for name, path in present.items()
    )


def _discard(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    for item in (path, *path.rglob("*")):
        if item.is_dir() and not item.is_symlink():
            item.chmod(0o755)
    shutil.rmtree(path, ignore_errors=True)


RUNNER: Final = (SANDBOX_DIR / "runner.py").read_text()
SOURCES: Final = read_sources(CONTAINER_ENTRY)

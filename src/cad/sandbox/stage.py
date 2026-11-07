import hashlib
import secrets
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from cad.sandbox.container import ReadOnlyMount

SANDBOX_DIR: Final = Path(__file__).parent
CHECKS_DIR: Final = Path(__file__).parents[1] / "checks" / "container"
PACKAGE_PATH: Final = "cad/checks/container"
STAGE_ROOT: Final = Path.home() / ".cad" / "stage"
DIGEST_CHARS: Final = 16
TARGET: Final = "/opt/trusted"
BOOT: Final = (
    f"import sys; sys.path.insert(0, {TARGET!r}); "
    "from cad.checks.container.runner import main; main()"
)


@dataclass(frozen=True, slots=True)
class Sources:
    files: Mapping[str, bytes]
    digest: str


def read_sources(directory: Path = CHECKS_DIR) -> Sources:
    files = {
        f"{PACKAGE_PATH}/{path.name}": path.read_bytes() for path in sorted(directory.glob("*.py"))
    }
    digest = hashlib.sha256()
    for path, data in files.items():
        digest.update(f"{path}\0".encode())
        digest.update(hashlib.sha256(data).digest())
    return Sources(files, digest.hexdigest())


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
        _discard(target)
        try:
            building.rename(target)  # macOS refuses to rename a directory it cannot write
        except OSError:
            if not _holds(target, sources):
                raise
        else:
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
SOURCES: Final = read_sources()

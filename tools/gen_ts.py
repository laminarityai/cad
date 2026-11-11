"""Generate `web/src/api/types.ts`, the web page's types for the person's routes.

The OpenAPI document comes from `cad.operations.openapi`, which reads the same registry that
mounts the routes, and `openapi-typescript` (pinned in `web/package-lock.json`) writes the types.
With `--check` nothing is written: the file is regenerated beside the committed one and the exit
status is 1 when they differ. That is the `api types` step of `uv run verify`.
"""

import argparse
import fcntl
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from cad.operations.openapi import document
from cad.operations.outside import every_route

WEB = Path(__file__).resolve().parents[1] / "web"
TYPES = WEB / "src" / "api" / "types.ts"
GENERATOR = WEB / "node_modules" / ".bin" / "openapi-typescript"
INSTALLED = WEB / "node_modules" / ".package-lock.json"
LOCK = WEB / "package-lock.json"
INSTALLING = WEB / ".install.lock"
NO_NODE = (
    "gen_ts: node and npm are not on PATH, and the api types step needs them. "
    "Install Node 22 or later (macOS: brew install node), then run it again."
)


def packages(lock: Path) -> dict[str, dict[str, object]]:
    document: dict[str, dict[str, dict[str, object]]] = json.loads(lock.read_text())
    return {path: entry for path, entry in document["packages"].items() if path}


def install_matches_lock() -> bool:
    """Whether `node_modules` holds what the lock says, judged by content, never by mtime.

    A fresh worktree checks the lock out with a new mtime. npm writes `.package-lock.json` as the
    lock's `packages` map without the root entry, and without the optional packages built for
    another platform, so every lock entry must be installed unless it is optional.
    """
    if not GENERATOR.exists():
        return False
    try:
        wanted, installed = packages(LOCK), packages(INSTALLED)
    except (OSError, ValueError, KeyError):
        return False
    return all(wanted.get(path) == entry for path, entry in installed.items()) and all(
        path in installed or entry.get("optional") is True for path, entry in wanted.items()
    )


def install_if_stale() -> None:
    """`verify` runs the web steps side by side, so the first one to take the lock installs and
    the others wait, then find the install fresh."""
    with INSTALLING.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if install_matches_lock():
            return
        subprocess.run(
            ["npm", "ci", "--no-audit", "--no-fund", "--prefix", str(WEB)],
            check=True,
            stdout=subprocess.DEVNULL,
        )


def generate(into: Path) -> None:
    with TemporaryDirectory() as scratch:
        described = Path(scratch) / "openapi.json"
        described.write_text(json.dumps(document(every_route()), indent=2))
        subprocess.run(
            [
                str(GENERATOR),
                str(described),
                "--root-types",
                "--root-types-no-schema-prefix",
                "--default-non-nullable",
                "false",
                "--output",
                str(into),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="gen_ts", description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args(argv)
    if shutil.which("node") is None or shutil.which("npm") is None:
        print(NO_NODE)
        return 1
    install_if_stale()
    if not args.check:
        generate(TYPES)
        return 0
    with TemporaryDirectory() as scratch:
        fresh = Path(scratch) / "types.ts"
        generate(fresh)
        if TYPES.exists() and TYPES.read_text() == fresh.read_text():
            return 0
    print(
        f"{TYPES.relative_to(WEB.parent)} is out of date with the registry. "
        "Run `uv run python tools/gen_ts.py` and commit it."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

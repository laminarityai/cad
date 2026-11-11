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


def holds(entry: dict[str, object] | None) -> tuple[object, ...] | None:
    """What an entry installs. npm on Linux drops other keys, such as `libc`, from the entries it
    writes into `node_modules`."""
    return entry and tuple(entry.get(key) for key in ("version", "resolved", "integrity", "link"))


def unlike_lock() -> list[str]:
    """The paths where `node_modules` does not hold what the lock says, judged by content, never
    by mtime.

    A fresh worktree checks the lock out with a new mtime. npm writes `.package-lock.json` as the
    lock's `packages` map without the root entry, and without the optional packages built for
    another platform, so every lock entry must be installed unless it is optional.
    """
    if not GENERATOR.exists():
        return [str(GENERATOR)]
    try:
        wanted, installed = packages(LOCK), packages(INSTALLED)
    except (OSError, ValueError, KeyError):
        return [str(INSTALLED)]
    changed = [path for path, entry in installed.items() if holds(wanted.get(path)) != holds(entry)]
    absent = [
        path
        for path, entry in wanted.items()
        if path not in installed and entry.get("optional") is not True
    ]
    return changed + absent


def install_matches_lock() -> bool:
    return not unlike_lock()


def install_if_stale() -> None:
    """`verify` runs the web steps side by side, so the first one to take the lock installs and
    the others wait, then find the install fresh. An install that still reads as stale would make
    every later step install again, under the steps already running, so it fails here."""
    with INSTALLING.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if install_matches_lock():
            return
        subprocess.run(
            ["npm", "ci", "--no-audit", "--no-fund", "--prefix", str(WEB)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        if unlike := unlike_lock():
            raise SystemExit(f"gen_ts: npm ci left node_modules unlike the lock at {unlike[:8]}")


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

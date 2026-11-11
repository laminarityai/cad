"""Stamps let a fast step that passed be skipped while its inputs stay the same.

A stamp is the digest of everything a step's result depends on: its name and argv, the Python
version, where its tools resolve on PATH, and the path and content of every file in the checkout
that one of its input patterns matches. The checkout's files are what git lists, tracked or
untracked, without the ignored ones, so a new file counts and `node_modules` does not; the
lockfiles stand in for what is installed.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

from cad.verify.steps import Step

CACHE = Path.home() / ".cache" / "cad" / "verify"


@dataclass(frozen=True, slots=True)
class Stamps:
    root: Path
    directory: Path
    files: dict[str, str]

    @classmethod
    def scan(cls, root: Path, cache: Path = CACHE) -> "Stamps":
        listed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, check=True,
        )  # fmt: skip
        files: dict[str, str] = {}
        for name in sorted(set(listed.stdout.decode().split("\0")) - {""}):
            path = root / name
            if path.is_file():
                files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        place = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        return cls(root, cache / place, files)

    def digest(self, step: Step) -> str | None:
        """None when the step declares no inputs, so it is never skipped."""
        if not step.inputs:
            return None
        hashed = hashlib.sha256()
        for part in (step.name, *step.argv, sys.version, *map(_located, step.tools)):
            hashed.update(part.encode() + b"\0")
        for name, content in self.files.items():
            if any(fnmatchcase(name, pattern) for pattern in step.inputs):
                hashed.update(f"{name}\0{content}\0".encode())
        return hashed.hexdigest()

    def passed(self, step: Step, digest: str) -> bool:
        if not all((self.root / output).exists() for output in step.outputs):
            return False
        try:
            return self._stamp(step).read_text() == digest
        except OSError:
            return False

    def record(self, step: Step, digest: str) -> None:
        stamp = self._stamp(step)
        stamp.parent.mkdir(parents=True, exist_ok=True)
        partial = stamp.with_suffix(f".{os.getpid()}.tmp")
        partial.write_text(digest)
        partial.replace(stamp)

    def clear(self, step: Step) -> None:
        self._stamp(step).unlink(missing_ok=True)

    def _stamp(self, step: Step) -> Path:
        return self.directory / f"{step.name.replace(' ', '-')}.stamp"


def _located(tool: str) -> str:
    found = shutil.which(tool)
    return os.path.realpath(found) if found else f"absent:{tool}"

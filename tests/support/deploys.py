"""What `TRUST_DIGEST` would be after a deploy that edits one source file, computed on a copy so
no test edits the source tree."""

import shutil
from pathlib import Path
from typing import Final

from cad.variants import entry

FOLDERS: Final = ("sandbox", "variants")


def copied(tmp_path: Path) -> Path:
    root = tmp_path / "deployed" / "cad"
    for folder in FOLDERS:
        shutil.copytree(
            entry.SOURCE / folder, root / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    return root


def digest_after_editing(tmp_path: Path, name: str) -> str:
    root = copied(tmp_path)
    with (root / name).open("a") as file:
        file.write("\n# a later deploy\n")
    digest = entry.trust_digest(root)
    shutil.rmtree(root.parent)
    return digest

import os
import subprocess
import sys
from pathlib import Path

MAX_LINES = 400


GENERATED = {Path("web/src/api/types.ts")}


def tracked_source_files() -> list[Path]:
    listed = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "*.py",
            "*.pyi",
            "*.ts",
            "*.tsx",
        ],
        capture_output=True,
        check=True,
    )
    paths = (Path(os.fsdecode(name)) for name in listed.stdout.split(b"\0") if name)
    return [path for path in paths if path.is_file() and path not in GENERATED]


def line_count(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] or tracked_source_files()
    counts = [(path, line_count(path)) for path in paths]
    failures = [(path, count) for path, count in counts if count > MAX_LINES]
    for path, count in failures:
        print(f"{path} has {count} lines, over the {MAX_LINES} line limit: split this file.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

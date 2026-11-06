import subprocess
import sys
from pathlib import Path

MAX_LINES = 400


def tracked_python_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line) for line in listed.stdout.splitlines() if Path(line).is_file()]


def main(argv: list[str]) -> int:
    paths = [Path(arg) for arg in argv] or tracked_python_files()
    counts = [(path, len(path.read_text().splitlines())) for path in paths]
    failures = [(path, count) for path, count in counts if count > MAX_LINES]
    for path, count in failures:
        print(f"{path} has {count} lines, over the {MAX_LINES} line limit: split this file.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

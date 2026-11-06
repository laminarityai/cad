import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_file_size.py"


def run_tool(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(path)], capture_output=True, text=True, check=False
    )


def write_lines(directory: Path, count: int) -> Path:
    path = directory / "sample.py"
    path.write_text("x = 1\n" * count)
    return path


def test_400_line_file_passes(tmp_path: Path) -> None:
    done = run_tool(write_lines(tmp_path, 400))
    assert done.returncode == 0
    assert done.stdout == ""


def test_401_line_file_fails_and_says_how_to_fix_it(tmp_path: Path) -> None:
    path = write_lines(tmp_path, 401)
    done = run_tool(path)
    assert done.returncode == 1
    assert str(path) in done.stdout
    assert "401 lines" in done.stdout
    assert "400 line limit" in done.stdout
    assert "split this file" in done.stdout


@pytest.mark.parametrize("count", [0, 1])
def test_short_files_pass(tmp_path: Path, count: int) -> None:
    assert run_tool(write_lines(tmp_path, count)).returncode == 0

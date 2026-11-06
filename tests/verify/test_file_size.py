import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_file_size.py"


def run_tool(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), str(path)], capture_output=True, text=True, check=False
    )


def run_tool_on_git_listing(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, text=True, check=False, cwd=repo
    )


def init_repo(directory: Path) -> Path:
    subprocess.run(["git", "init", "--quiet", str(directory)], check=True)
    return directory


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


@pytest.mark.parametrize("name", ["café.py", 'a"b.py', "tab\there.py", "новый.py"])
def test_git_listing_checks_files_whose_names_git_quotes(tmp_path: Path, name: str) -> None:
    repo = init_repo(tmp_path)
    (repo / name).write_text("x = 1\n" * 401)
    done = run_tool_on_git_listing(repo)
    assert done.returncode == 1
    assert name in done.stdout
    assert "401 lines" in done.stdout


def test_git_listing_checks_type_stubs(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "stub.pyi").write_text("x: int\n" * 401)
    done = run_tool_on_git_listing(repo)
    assert done.returncode == 1
    assert "stub.pyi has 401 lines" in done.stdout


def test_git_listing_ignores_tracked_files_deleted_from_the_working_tree(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    (repo / "gone.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(repo), "add", "gone.py"], check=True)
    (repo / "gone.py").unlink()
    assert run_tool_on_git_listing(repo).returncode == 0


LINE_BREAKS_PYTHON_SPLITS_ON = [
    "\x0c",
    "\x0b",
    "\x1c",
    "\x1d",
    "\x1e",
    "\x85",
    chr(0x2028),
    chr(0x2029),
]


@pytest.mark.parametrize("separator", LINE_BREAKS_PYTHON_SPLITS_ON)
def test_only_newlines_count_as_lines(tmp_path: Path, separator: str) -> None:
    path = tmp_path / "sample.py"
    path.write_text(f"x = '{separator}'\n" * 400, encoding="utf-8")
    assert run_tool(path).returncode == 0


@pytest.mark.parametrize(
    ("text", "passes"),
    [
        ("x = 1\n" * 400, True),
        ("x = 1\n" * 399 + "x = 1", True),
        ("x = 1\r\n" * 400, True),
        ("x = 1\r\n" * 399 + "x = 1", True),
        ("x = 1\n" * 401, False),
        ("x = 1\n" * 400 + "x = 1", False),
        ("x = 1\r\n" * 401, False),
    ],
)
def test_line_count_ignores_trailing_newline_and_crlf(
    tmp_path: Path, text: str, passes: bool
) -> None:
    path = tmp_path / "sample.py"
    path.write_bytes(text.encode())
    assert (run_tool(path).returncode == 0) is passes

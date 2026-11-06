import subprocess
from pathlib import Path

from cad.server.app import GitState, git_state

GIT = ("git", "-c", "user.name=t", "-c", "user.email=t@t")


def run_git(root: Path, *args: str) -> str:
    done = subprocess.run((*GIT, *args), cwd=root, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def make_repo(root: Path) -> str:
    run_git(root, "init", "-q")
    run_git(root, "commit", "-q", "--allow-empty", "-m", "first")
    return run_git(root, "rev-parse", "HEAD")


def test_clean_repo_reports_head_and_not_dirty(tmp_path: Path) -> None:
    head = make_repo(tmp_path)
    assert git_state(tmp_path) == GitState(sha=head, dirty=False)


def test_untracked_file_makes_it_dirty(tmp_path: Path) -> None:
    head = make_repo(tmp_path)
    (tmp_path / "new.txt").write_text("x")
    assert git_state(tmp_path) == GitState(sha=head, dirty=True)


def test_modified_tracked_file_makes_it_dirty(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("1")
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "add", "a.txt")
    run_git(tmp_path, "commit", "-q", "-m", "first")
    (tmp_path / "a.txt").write_text("2")
    assert git_state(tmp_path).dirty


def test_outside_git_is_unknown(tmp_path: Path) -> None:
    assert git_state(tmp_path) == GitState(sha="unknown", dirty=False)


def test_directory_inside_a_parent_repo_is_unknown_not_the_parents_sha(tmp_path: Path) -> None:
    make_repo(tmp_path)
    nested = tmp_path / "nested"
    nested.mkdir()
    assert git_state(nested).sha == "unknown"

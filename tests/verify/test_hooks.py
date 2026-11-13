import subprocess
from pathlib import Path

from cad.verify.__main__ import hooks_missing


def git(cwd: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True)


def clone(path: Path) -> Path:
    path.mkdir()
    git(path, "init", "-q")
    git(
        path,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    return path


def test_a_clone_without_the_hooks_is_told_how_to_install_them(tmp_path: Path) -> None:
    assert hooks_missing(clone(tmp_path / "repo"))


def test_a_worktree_shares_the_hooks_its_clone_installed(tmp_path: Path) -> None:
    repo = clone(tmp_path / "repo")
    (repo / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
    git(repo, "worktree", "add", "-q", str(repo / ".claude" / "worktrees" / "agent"))
    assert not hooks_missing(repo / ".claude" / "worktrees" / "agent")


def test_a_directory_outside_git_is_not_warned(tmp_path: Path) -> None:
    assert not hooks_missing(tmp_path)

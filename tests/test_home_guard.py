import os
import pwd
import threading
from pathlib import Path

import pytest

from cad.records.roots import HOME_ROOTS

OPERATOR = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".cad"


@pytest.mark.parametrize(
    "target",
    [HOME_ROOTS.briefs, HOME_ROOTS.projects, OPERATOR / "projects"],
    ids=["briefs", "projects", "operator projects"],
)
def test_a_write_under_the_operators_cad_is_refused_and_named(
    target: Path, home_writes: list[str]
) -> None:
    missing = target / "no-such-directory" / "record.signed"
    with pytest.raises(PermissionError, match="give it tmp_path roots"):
        missing.write_bytes(b"x")
    with pytest.raises(PermissionError):
        (missing.parent / "deeper").mkdir()
    assert home_writes == [f"open {missing}", f"os.mkdir {missing.parent / 'deeper'}"]
    home_writes.clear()


def test_reads_and_the_sandbox_stage_are_not_refused(home_writes: list[str]) -> None:
    assert not (HOME_ROOTS.briefs / "no-such-directory").exists()
    with pytest.raises(FileNotFoundError):
        (HOME_ROOTS.briefs / "no-such-directory" / "x").read_bytes()
    with pytest.raises(FileNotFoundError):
        (Path.home() / ".cad" / "stage" / "no-such-directory" / "x").write_bytes(b"x")
    assert home_writes == []


def test_a_write_through_a_symlink_or_a_case_variant_is_refused(
    tmp_path: Path, home_writes: list[str]
) -> None:
    link = tmp_path / "home"
    link.symlink_to(Path.home())
    targets = [link / ".cad" / "briefs" / "record.signed", OPERATOR.parent / ".CAD" / "record"]
    for target in targets:
        with pytest.raises(PermissionError, match="give it tmp_path roots"):
            target.write_bytes(b"x")
    assert len(home_writes) == 2
    home_writes.clear()


def test_a_write_from_another_thread_is_recorded(home_writes: list[str]) -> None:
    refused: list[BaseException] = []

    def write() -> None:
        try:
            (HOME_ROOTS.briefs / "no-such-directory" / "x").write_bytes(b"x")
        except PermissionError as error:
            refused.append(error)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert (len(refused), len(home_writes)) == (8, 8)
    home_writes.clear()

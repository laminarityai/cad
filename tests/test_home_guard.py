import os
import pwd
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

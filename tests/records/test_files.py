import errno
import os
from pathlib import Path

import pytest

from cad.errors import Unavailable
from cad.records import signed
from cad.records.signed import Store


def test_a_read_that_fails_once_is_unavailable_not_tampered_and_the_next_read_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    things = Store(tmp_path / "things", "thing")
    path = things.root / "a" / "0001.signed"
    assert signed.publish(things, "thing/1", path, b"a record")
    real_open = os.open
    failed: list[str] = []

    def open_failing_once(file: str | os.PathLike[str], flags: int, *args: int) -> int:
        if Path(file) == path and not failed:
            failed.append(str(file))
            raise OSError(errno.EIO, "Input/output error", str(file))
        return real_open(file, flags, *args)

    monkeypatch.setattr(os, "open", open_failing_once)
    with pytest.raises(Unavailable, match="try again"):
        signed.read(things, "thing/1", path)
    assert signed.read(things, "thing/1", path) == b"a record"
    assert signed.read(things, "thing/1", path.with_name("0002.signed")) is None
    path.with_name("0003.signed").symlink_to(path)
    assert signed.read(things, "thing/1", path.with_name("0003.signed")) is None

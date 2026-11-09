import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cad.sandbox.stage import Sources, materialize

STAGERS = 8
ROUNDS = 200
SOURCES = Sources({f"cad/m{i}.py": b"x = 1\n" for i in range(3)}, "0" * 64, {})


def stage_together(root: Path) -> list[str]:
    start = threading.Barrier(STAGERS)

    def stage_and_read(_: int) -> str | None:
        start.wait()
        try:
            staged = materialize(SOURCES, root)
            changed = [n for n, data in SOURCES.files.items() if (staged / n).read_bytes() != data]
        except OSError as error:
            return repr(error)
        return f"changed: {changed}" if changed else None

    with ThreadPoolExecutor(STAGERS) as pool:
        return [failed for failed in pool.map(stage_and_read, range(STAGERS)) if failed]


def test_stagers_racing_for_one_digest_each_get_a_directory_nobody_removes(
    tmp_path: Path,
) -> None:
    failures = [stage_together(tmp_path / str(round)) for round in range(ROUNDS)]
    assert [failed for failed in failures if failed] == []

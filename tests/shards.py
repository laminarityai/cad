"""Split the test files into CI's parallel jobs. CAD_TEST_SHARD=index/count keeps one shard.

A file stays whole, so its module fixtures still run once. Each file weighs its seconds in
shard_seconds.json, and the heaviest goes first onto the lightest shard, so the shards end close
together. A file the table lacks weighs DEFAULT_SECONDS.

Within a run the heaviest file is queued first too, so under `-n 4 --dist loadfile` a long file
starts at once instead of after the short ones; xdist's own reorder, by test count, is turned off.

CAD_TEST_SECONDS=<path> writes each file's summed test seconds there. Every CI shard uploads its
file as the artifact shard-seconds-<n>. To refresh the table, merge one run's artifacts:

    gh run download <run id> --pattern 'shard-seconds-*' --dir <dir>
    jq -sS add <dir>/*/shard-seconds.json > tests/shard_seconds.json
"""

import json
import os
from collections import defaultdict
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Final

import pytest

TABLE: Final = Path(__file__).with_name("shard_seconds.json")
DEFAULT_SECONDS: Final = 1.0
MIN_RECORDED_SECONDS: Final = 2.0


def shard_of(files: Collection[str], seconds: Mapping[str, float], count: int) -> dict[str, int]:
    def weight(name: str) -> float:
        return seconds.get(name, DEFAULT_SECONDS)

    loads = [0.0] * count
    placed: dict[str, int] = {}
    for name in sorted(files, key=lambda name: (-weight(name), name)):
        lightest = loads.index(min(loads))
        placed[name] = lightest
        loads[lightest] += weight(name)
    return placed


def file_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def pytest_configure(config: pytest.Config) -> None:
    if hasattr(config.option, "loadscopereorder"):
        config.option.loadscopereorder = False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    seconds: dict[str, float] = json.loads(TABLE.read_text())
    items.sort(key=lambda item: -seconds.get(file_of(item.nodeid), DEFAULT_SECONDS))
    shard = os.environ.get("CAD_TEST_SHARD")
    if not shard:
        return
    index, count = (int(part) for part in shard.split("/"))
    placed = shard_of({file_of(item.nodeid) for item in items}, seconds, count)
    kept: list[pytest.Item] = []
    dropped: list[pytest.Item] = []
    for item in items:
        (kept if placed[file_of(item.nodeid)] == index - 1 else dropped).append(item)
    config.hook.pytest_deselected(items=dropped)
    items[:] = kept


spent: defaultdict[str, float] = defaultdict(float)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    spent[file_of(report.nodeid)] += report.duration


def pytest_sessionfinish(session: pytest.Session) -> None:
    out = os.environ.get("CAD_TEST_SECONDS")
    if out is None or hasattr(session.config, "workerinput"):
        return
    table = {
        name: round(total) for name, total in sorted(spent.items()) if total >= MIN_RECORDED_SECONDS
    }
    Path(out).write_text(json.dumps(table, indent=2) + "\n")

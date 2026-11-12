import hashlib
import json
import os
import secrets
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

import pytest
from cache_key import CORE, shared_inputs
from cases import BY_NAME, CASES, Case

from cad.checks.container.mesher import MESH_CHANGE_LIMIT
from cad.checks.report import IMAGE_TAG
from cad.sandbox import container
from cad.sandbox.container import Job, ReadOnlyMount
from cad.sandbox.host import Artifacts, build
from cad.sandbox.image import BUILD, current_image, image_tag
from cad.sandbox.stage import TARGET, check_mount

pytestmark = pytest.mark.docker

HARNESS: Final = "/opt/fea"
PROGRAM: Final = (
    f"import sys; sys.path[:0] = [{TARGET!r}, {HARNESS!r}]; from driver import main; main()"
)
DETERMINISM_CASE: Final = "cantilever tip"
OVER_CAP_CASE: Final = "filleted cantilever tip"
CACHE: Final = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "cad" / "fea"


def brep_of(case: Case) -> bytes:
    built = build(case.code, current_image(image_tag(BUILD)))
    assert isinstance(built.verdict, Artifacts), built.output
    return built.verdict.brep


def solve_job(case: Case, brep: bytes) -> Job:
    return Job(
        "check",
        current_image(IMAGE_TAG),
        ("python", "-I", "-c", PROGRAM, case.name),
        brep,
        (check_mount(CORE), ReadOnlyMount(Path(__file__).parent, HARNESS)),
        wall_seconds=600,
        memory_mb=2048,
        tmpfs_mb=768,
    )


def solve(case: Case, brep: bytes) -> bytes:
    job = solve_job(case, brep)
    ran = container.run(job)
    assert ran.state.ExitCode == 0, ran.attended.output
    assert isinstance(ran.attended.report, bytes), ran.attended.output
    return ran.attended.report


def key(job: Job) -> str:
    """Digest every input the solve container can read, so equal keys mean equal reports.

    The container has no network and a read-only root. It reads only the image, its argv, stdin
    and the two mounts, which shared_inputs digests by content. The determinism test below proves
    equal inputs give equal bytes.
    """
    digest = hashlib.sha256()
    limits = f"{job.wall_seconds} {job.memory_mb} {job.tmpfs_mb}"
    for text in (job.image_id, *job.command, limits, shared_inputs()):
        digest.update(hashlib.sha256(text.encode()).digest())
    digest.update(hashlib.sha256(job.stdin).digest())
    return digest.hexdigest()


def cached_solve(case: Case, brep: bytes) -> bytes:
    stored = CACHE / key(solve_job(case, brep))
    if stored.is_file():
        return stored.read_bytes()
    report = solve(case, brep)
    CACHE.mkdir(parents=True, exist_ok=True)
    writing = CACHE / f".{stored.name}.{secrets.token_hex(8)}"
    writing.write_bytes(report)
    writing.replace(stored)
    return report


@pytest.fixture(scope="module")
def breps() -> Mapping[str, bytes]:
    with ThreadPoolExecutor(2) as pool:
        return dict(zip(BY_NAME, pool.map(brep_of, CASES), strict=True))


@pytest.fixture(scope="module")
def reports(breps: Mapping[str, bytes]) -> Mapping[str, bytes]:
    with ThreadPoolExecutor(2) as pool:
        solved = pool.map(cached_solve, CASES, (breps[case.name] for case in CASES))
        return dict(zip(BY_NAME, solved, strict=True))


def mesh(report: bytes, which: str) -> dict[str, float]:
    whole = json.loads(report)
    assert "failed" not in whole, whole["failed"]
    found = whole[which]
    assert "failed" not in found, found["failed"]
    return found


@pytest.mark.parametrize("name", list(BY_NAME))
def test_the_fine_mesh_matches_the_hand_calculation(
    name: str, reports: Mapping[str, bytes]
) -> None:
    case = BY_NAME[name]
    fine = mesh(reports[name], "fine")
    measured = fine[case.measure]
    error = (measured - case.expected) / case.expected
    print(
        f"\n{name:<24} {case.measure:<16} expected {case.expected:.6g}  measured {measured:.6g}"
        f"  error {error:+.2%}  tolerance {case.tolerance:.0%}  nodes {fine['nodes']:.0f}"
        f"  ({case.reference})"
    )
    assert abs(error) <= case.tolerance


@pytest.mark.parametrize("name", list(BY_NAME))
def test_the_coarse_and_fine_mesh_agree_within_the_fea_gate(
    name: str, reports: Mapping[str, bytes]
) -> None:
    coarse = mesh(reports[name], "coarse")["max_displacement"]
    fine = mesh(reports[name], "fine")["max_displacement"]
    assert abs(fine - coarse) / fine <= MESH_CHANGE_LIMIT


def test_only_the_part_over_the_node_cap_is_meshed_with_the_floor(
    reports: Mapping[str, bytes],
) -> None:
    floored = {name: json.loads(report)["over_cap"] for name, report in reports.items()}
    assert {name for name, over_cap in floored.items() if over_cap} == {OVER_CAP_CASE}
    assert "above the cap of 150000" in floored[OVER_CAP_CASE]


def test_solving_the_same_case_twice_gives_the_same_bytes(
    breps: Mapping[str, bytes], reports: Mapping[str, bytes]
) -> None:
    case = BY_NAME[DETERMINISM_CASE]
    assert solve(case, breps[case.name]) == reports[case.name]

"""The variant view lists each part the person supplied that the build placed, with its own mesh,
read by the BREP's SHA-256 like a variant's (ADR-0012)."""

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from cad.accounts.principal import AccountId, PersonSession
from cad.geometry import job
from cad.geometry import store as meshes
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Tessellated, TessellationFailed
from cad.operations.components import components
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.sandbox.outcome import PartPlacement, PartUse
from cad.uploads import store as uploads
from cad.uploads.model import kind_of
from tests.support.rows import RAIL, fake_ingest

PERSON = PersonSession(account=AccountId("user_alice"), session_id="sess_1")
SHA = hashlib.sha256(RAIL).hexdigest()
CORNER = PartPlacement(at=(40.0, 25.0, 0.0), rotate=(90.0, 0.0, 0.0))


def mesh_of(brep: bytes, brep_sha256: str) -> job.Ran:
    assert brep == RAIL
    bb = {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1}
    shapes: dict[str, object] = {
        "version": 3,
        "id": "/w",
        "name": "w",
        "parts": [],
        "loc": ((0, 0, 0), (0, 0, 0, 1)),
    }
    read = Tessellated.model_validate(
        {
            "brep_sha256": brep_sha256,
            "version": job.VERSION,
            "shapes": {**shapes, "normal_len": 0, "bb": bb},
            "topology": {"faces": [], "edges": []},
        }
    )
    return job.Ran(read, True)


@pytest.fixture
def wheel(roots: Roots) -> PartUse:
    project = new_project_id()
    kind = kind_of("wheel.step")
    part = uploads.add_part(
        roots.projects, project, "wheel.step", kind, None, RAIL, PERSON, fake_ingest
    )
    return PartUse(part_id=part.record.id, project=project, brep_sha256=SHA, placements=(CORNER,))


def test_a_placed_part_is_listed_with_its_mesh_and_placements(
    roots: Roots, tmp_path: Path, wheel: PartUse, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TESSELLATIONS, "_run", mesh_of)
    geometry = tmp_path / "geometry"
    first = components(roots, geometry, (wheel,))
    assert [(one.part_id, one.placements) for one in first] == [(wheel.part_id, (CORNER,))]
    assert first[0].mesh in {"pending", "tessellated"}
    TESSELLATIONS.read(geometry, _Held(RAIL, SHA), wait_seconds=5)
    (again,) = components(roots, geometry, (wheel,))
    assert (again.mesh, again.mesh_url) == ("tessellated", f"/v1/geometry/{job.VERSION}/{SHA}.json")
    assert meshes.read(geometry, SHA) is not None


def test_a_part_the_build_only_read_is_not_drawn(
    roots: Roots, tmp_path: Path, wheel: PartUse
) -> None:
    read_only = wheel.model_copy(update={"placements": ()})
    assert components(roots, tmp_path / "geometry", (read_only,)) == ()


def test_a_part_whose_brep_is_gone_has_a_failed_mesh(
    roots: Roots, tmp_path: Path, wheel: PartUse
) -> None:
    lost = wheel.model_copy(update={"brep_sha256": "e" * 64})
    (one,) = components(roots, tmp_path / "geometry", (lost,))
    assert (one.mesh, one.mesh_url) == ("failed", None)


def timed_out(brep: bytes, brep_sha256: str) -> job.Ran:
    failed = TessellationFailed(brep_sha256=brep_sha256, version=job.VERSION, reason="timed out")
    return job.Ran(failed, lasting=False)


def test_a_mesh_job_that_failed_briefly_is_reported_failed_not_pending_forever(
    roots: Roots, tmp_path: Path, wheel: PartUse, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs: list[str] = []

    def counted(brep: bytes, brep_sha256: str) -> job.Ran:
        jobs.append(brep_sha256)
        return timed_out(brep, brep_sha256)

    monkeypatch.setattr(TESSELLATIONS, "_run", counted)
    geometry = tmp_path / "geometry"
    states: list[tuple[str, str | None]] = []
    for _ in range(200):
        (one,) = components(roots, geometry, (wheel,))
        states.append((one.mesh, one.mesh_url))
        if one.mesh != "pending":
            break
        time.sleep(0.01)
    assert (states[-1], len(jobs)) == (("failed", None), 1)
    assert meshes.read(geometry, SHA) is None


def test_the_view_names_no_part_from_a_record_the_agent_can_write(
    roots: Roots, tmp_path: Path, wheel: PartUse
) -> None:
    (one,) = components(roots, tmp_path / "geometry", (wheel,))
    assert set(one.model_dump()) == {"part_id", "brep_sha256", "mesh", "mesh_url", "placements"}


@dataclass(frozen=True)
class _Held:
    brep: bytes
    brep_sha256: str

import hashlib
import threading

import pytest

from cad.accounts.principal import AccountId
from cad.geometry import job
from cad.geometry.lane import TESSELLATIONS
from cad.geometry.model import Tessellated
from cad.operations import reads
from cad.operations.model import Tenant
from cad.operations.tenants import Tenants
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built, NoResult
from cad.variants import entry

RAIL = b"CASCADE Topology V3, a rail\n"
SHA = hashlib.sha256(RAIL).hexdigest()
MESH = Tessellated.model_validate(
    {
        "brep_sha256": SHA,
        "version": job.VERSION,
        "shapes": {
            "version": 3,
            "id": "/rail",
            "name": "rail",
            "parts": [],
            "loc": ((0, 0, 0), (0, 0, 0, 1)),
            "normal_len": 0,
            "bb": {"xmin": 0, "xmax": 1, "ymin": 0, "ymax": 1, "zmin": 0, "zmax": 1},
        },
        "topology": {"faces": [], "edges": []},
    }
)


class Gated:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.started = threading.Event()
        self.gate = threading.Event()

    def __call__(self, brep: bytes, brep_sha256: str) -> job.Ran:
        assert brep == RAIL
        self.calls.append(brep_sha256)
        self.started.set()
        self.gate.wait(5)
        return job.Ran(MESH, True)


@pytest.fixture
def alice(tenants: Tenants) -> Tenant:
    return tenants.of(AccountId("user_alice"))


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch) -> Gated:
    gated = Gated()
    monkeypatch.setattr(TESSELLATIONS, "_run", gated)
    return gated


def stored_build(tenant: Tenant, code: str, outcome: Built | NoResult) -> str:
    vid = entry.variant_id(code, image_tag(BUILD))
    brep = RAIL if isinstance(outcome, Built) else None
    entry.save(tenant.variants, vid, code, Build(outcome=outcome, output=""), brep)
    return vid


def test_view_starts_the_mesh_it_reports_pending_when_no_job_is_making_it(
    alice: Tenant, run: Gated
) -> None:
    vid = stored_build(alice, "result = 2", Built())
    asked = reads.VariantInput(variant_id=vid)
    assert [reads.view(alice, asked).mesh for _ in range(3)] == ["pending"] * 3
    assert run.started.wait(5)
    assert run.calls == [SHA]

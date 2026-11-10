from pathlib import Path

import pytest

from cad.accounts.tenants import open_tenant
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.geometry.lane import Tessellations
from cad.geometry.model import Tessellated, TessellationFailed, mesh_volume
from cad.operations.geometry import GeometryInput, geometry
from cad.records.roots import Roots
from cad.sandbox import image
from cad.sandbox.host import run_checks
from cad.sandbox.outcome import Built
from cad.server.app import LOCAL
from cad.variants import entry
from cad.variants.entry import UnknownVariant
from cad.variants.store import build_variant

PARTS = Path(__file__).parents[1] / "sandbox/parts"
AGREEMENT = 0.005


@pytest.mark.parametrize("part", ["plate", "spur_gear", "hex_spacer"])
def test_the_mesh_encloses_the_volume_the_mass_check_measured(part: str, tmp_path: Path) -> None:
    built = build_variant((PARTS / f"{part}.py").read_text(), tmp_path / "variants")
    assert built.outcome == Built(), built.output
    checked = run_checks(built.variant_id, "prusament-pla", tmp_path / "variants")
    volume = checked.result("mass").number("volume", "mm^3")
    held = entry.open_entry(tmp_path / "variants", built.variant_id, image.image_tag(image.BUILD))
    assert held.brep_sha256 == checked.brep_sha256
    read = Tessellations().read(tmp_path / "geometry", held, wait_seconds=60)
    assert isinstance(read, Tessellated), read
    assert read.brep_sha256 == checked.brep_sha256
    meshed = mesh_volume(read.shapes["parts"][0]["shape"])
    assert abs(meshed - volume) <= AGREEMENT * volume, (meshed, volume)


def test_a_brep_the_kernel_cannot_read_fails_and_is_stored(tmp_path: Path) -> None:
    held = entry.Entry(entry.VariantId("0123456789abcdef"), tmp_path, b"not a brep", "0" * 64)
    read = Tessellations().read(tmp_path / "geometry", held, wait_seconds=60)
    assert isinstance(read, TessellationFailed), read
    assert "could not be tessellated" in read.reason
    assert (
        Tessellations(lambda brep, sha: pytest.fail("ran again")).read(tmp_path / "geometry", held)
        == read
    )


def test_the_geometry_of_an_unknown_variant_is_refused(tmp_path: Path) -> None:
    roots = Roots(tmp_path / "briefs", tmp_path / "projects")
    tenant = open_tenant(
        LOCAL, roots, tmp_path / "variants", tmp_path / "geometry", None, Door(), ingest
    )
    with pytest.raises(UnknownVariant, match="0123456789abcdef"):
        geometry(tenant, GeometryInput(variant_id="0123456789abcdef"))

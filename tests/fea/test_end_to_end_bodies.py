"""The stress check on a variant of two bodies, through the scorecard: the named body is solved
alone, in its own material, and its faces are the whole variant's."""

from pathlib import Path
from typing import Any

import pytest
from cases import BEAM_P, MOUNTED_BEAM_CODE, timoshenko_tip
from pydantic import TypeAdapter

from cad.checks import jobs
from cad.checks.container import lone
from cad.checks.container.calculix import Material
from cad.checks.lanes import Lanes
from cad.checks.result import BodyMaterial, CheckResult, Verdict
from cad.geometry import job as tessellation
from cad.geometry.model import Tessellated
from cad.loads.model import LoadCase
from cad.sandbox import image
from cad.sandbox.outcome import Built
from cad.scorecard import score
from cad.scorecard.model import JOINTS, Scorecard
from cad.tables.materials import Known, load_materials, magnitude
from cad.variants import entry
from cad.variants.store import build_variant

pytestmark = pytest.mark.docker

BEAM, BLOCK = "cliffs-304", "bambu-pla-cf"
MATERIALS = (BodyMaterial(body="block", key=BLOCK), BodyMaterial(body="beam", key=BEAM))
CASE: dict[str, Any] = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": BEAM_P, "unit": "N"},
        "direction": {"kind": "across", "axis": "long"},
    },
}
CASES = TypeAdapter(LoadCase)


def scored(variant: str, root: Path, case: LoadCase) -> CheckResult:
    demand = jobs.Demand(loads={case.id: case.wire()})
    lanes = Lanes(jobs.run_job)
    card = score.score_variant(variant, MATERIALS, root, lanes=lanes, demand=demand)
    for _ in range(40):
        if not card.pending:
            break
        card = score.score_variant(variant, MATERIALS, root, lanes=lanes, demand=demand)
    assert card.pending == ()
    assert card.untested == (JOINTS,)
    return fea_of(card)


def fea_of(card: Scorecard) -> CheckResult:
    (found,) = (one for one in card.finished if one.check_id == "fea")
    return found


def steel() -> Material:
    row = load_materials().get_material(BEAM)
    assert isinstance(row.elastic_modulus, Known)
    assert isinstance(row.poisson_ratio, Known)
    return Material(
        row.elastic_modulus.magnitude_in("MPa"), row.poisson_ratio.magnitude_in("dimensionless")
    )


def test_the_named_body_is_solved_alone_in_its_material_on_its_own_faces(tmp_path: Path) -> None:
    built = build_variant(MOUNTED_BEAM_CODE, tmp_path)
    assert isinstance(built.outcome, Built), built.output
    found = scored(built.variant_id, tmp_path, CASES.validate_python({**CASE, "body": "beam"}))
    assert found.verdict == Verdict.PASS, found.reason
    assert found.reason.startswith("solved the body beam alone, in its own material: ")
    hand = timoshenko_tip(steel())
    measured = magnitude(found.value("max_displacement"), "mm")
    print(f"fea max_displacement {measured:.4f} mm, hand {hand:.4f} mm")
    assert measured == pytest.approx(hand, rel=0.03)
    assert magnitude(found.value("elastic_modulus:beam"), "MPa") == steel().elastic_modulus
    held = entry.open_entry(tmp_path, built.variant_id, image.image_tag(image.BUILD))
    ran = tessellation.tessellate(held.brep, held.brep_sha256)
    assert isinstance(ran.read, Tessellated)
    block, beam = ran.read.solid_faces
    assert found.where is not None
    assert {*found.where.support, *found.where.load} <= set(range(block, block + beam))


def test_a_load_case_that_names_no_body_on_two_bodies_is_unknown_and_says_why(
    tmp_path: Path,
) -> None:
    built = build_variant(MOUNTED_BEAM_CODE, tmp_path)
    assert isinstance(built.outcome, Built), built.output
    found = scored(built.variant_id, tmp_path, CASES.validate_python(CASE))
    assert found.verdict == Verdict.UNKNOWN
    assert lone.NAME_ONE in found.reason
    assert found.measured == ()

import dataclasses
from pathlib import Path

import pytest
from cases import BEAM_B, BEAM_H, BEAM_L, BEAM_P, STEEL, box, timoshenko_tip
from pydantic import TypeAdapter

from cad.briefs.model import BriefId, Requirement, RequirementId, Target
from cad.briefs.origins import BriefSpan
from cad.checks import jobs
from cad.checks.container.calculix import Material
from cad.checks.container.fea import CLAMPED_FACE_NOTE, LARGE_DISPLACEMENT_FRACTION, STIFFER
from cad.checks.lanes import Lanes
from cad.checks.result import CheckResult, Verdict
from cad.geometry import job as tessellation
from cad.geometry.model import Tessellated
from cad.loads.model import LoadCase
from cad.sandbox import host, image
from cad.sandbox.outcome import Built
from cad.scorecard import requirements, score
from cad.scorecard.model import AgainstBrief, Basis, Checked, Scorecard
from cad.tables.materials import UNITS, Known, MaterialsTable, load_materials, magnitude
from cad.variants import entry
from cad.variants.store import build_variant

pytestmark = pytest.mark.docker

KEY = "prusament-pla"
CASE = {
    "support": {"kind": "flat_end"},
    "load": {
        "kind": "far_end",
        "force": {"magnitude": BEAM_P, "unit": "N"},
        "direction": {"kind": "across", "axis": "long"},
    },
}
TARGET = TypeAdapter[Target](Target)


def table_with_steel_stiffness() -> MaterialsTable:
    table = load_materials()
    row = table.get_material(KEY)
    assert isinstance(row.density, Known)
    source = row.density.source
    stiff = dataclasses.replace(
        row,
        elastic_modulus=Known(UNITS.Quantity(STEEL.elastic_modulus, "MPa"), source),
        poisson_ratio=Known(UNITS.Quantity(STEEL.poisson_ratio, "dimensionless"), source),
    )
    return dataclasses.replace(table, materials={**table.materials, KEY: stiff})


def deflection(rid: str, mm: float) -> Requirement:
    raw = {"kind": "max_deflection", "load": CASE, "deflection": {"magnitude": mm, "unit": "mm"}}
    return Requirement(
        id=RequirementId(rid * 16),
        brief_id=BriefId("1" * 16),
        target=TARGET.validate_python(raw),
        origin=BriefSpan(start=0, end=1),
    )


def test_the_cantilever_deflection_verdicts_match_the_hand_calc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(host, "materials_table", table_with_steel_stiffness)
    built = build_variant(box(BEAM_L, BEAM_B, BEAM_H), tmp_path)
    assert built.outcome == Built(), built.output
    hand = timoshenko_tip(STEEL)
    above, below = deflection("a", 1.1 * hand), deflection("b", 0.9 * hand)

    def assess(results: score.Results) -> Basis:
        return requirements.assess_requirements("1" * 16, "d" * 64, (above, below), results)

    case = TypeAdapter(LoadCase).validate_python(CASE)
    card = scored(built.variant_id, tmp_path, assess)
    found = fea_result(card)
    assert found.instance == case.id
    assert found.verdict == Verdict.PASS, found.reason
    assert CLAMPED_FACE_NOTE in found.reason
    measured = magnitude(found.value("max_displacement"), "mm")
    print(f"fea max_displacement {measured:.4f} mm, hand {hand:.4f} mm")
    assert measured == pytest.approx(hand, rel=0.03)
    assert isinstance(card.basis, AgainstBrief)
    verdicts = [one.verdict for one in card.basis.requirements if isinstance(one, Checked)]
    assert verdicts == [Verdict.PASS, Verdict.FAIL]
    held = entry.open_entry(tmp_path, built.variant_id, image.image_tag(image.BUILD))
    ran = tessellation.tessellate(held.brep, held.brep_sha256)
    assert isinstance(ran.read, Tessellated)
    ends = face_ends_along_x(ran.read)
    assert found.where is not None
    (support,), (load,) = found.where.support, found.where.load
    assert {support, load} == set(ends)
    assert all(one.where is None for one in card.finished if one.check_id != "fea")


def test_a_pla_cantilever_that_bends_past_the_linear_gate_is_unknown_and_told_to_stiffen(
    tmp_path: Path,
) -> None:
    built = build_variant(box(BEAM_L, BEAM_B, BEAM_H), tmp_path)
    assert built.outcome == Built(), built.output
    pla = load_materials().get_material(KEY)
    assert isinstance(pla.elastic_modulus, Known)
    assert isinstance(pla.poisson_ratio, Known)
    hand = timoshenko_tip(
        Material(
            pla.elastic_modulus.magnitude_in("MPa"),
            pla.poisson_ratio.magnitude_in("dimensionless"),
        )
    )
    assert hand > LARGE_DISPLACEMENT_FRACTION * BEAM_L

    def assess(results: score.Results) -> Basis:
        return requirements.assess_requirements("1" * 16, "d" * 64, (deflection("a", 2),), results)

    card = scored(built.variant_id, tmp_path, assess)
    found = fea_result(card)
    assert found.verdict == Verdict.UNKNOWN
    assert found.reason.startswith("the part deforms")
    assert STIFFER in found.reason
    measured = magnitude(found.value("max_displacement"), "mm")
    print(f"fea max_displacement {measured:.4f} mm, hand {hand:.4f} mm")
    assert measured == pytest.approx(hand, rel=0.03)
    assert isinstance(card.basis, AgainstBrief)
    (row,) = card.basis.requirements
    assert isinstance(row, Checked)
    assert row.verdict == Verdict.UNKNOWN


def scored(variant: str, root: Path, assess: score.Assess) -> Scorecard:
    case = TypeAdapter(LoadCase).validate_python(CASE)
    demand = jobs.Demand(loads={case.id: case.wire()})
    lanes = Lanes(jobs.run_job)
    card = score.score_variant(variant, KEY, root, assess, lanes, demand=demand)
    for _ in range(40):
        if not card.pending:
            break
        card = score.score_variant(variant, KEY, root, assess, lanes, demand=demand)
    assert card.pending == ()
    return card


def face_ends_along_x(read: Tessellated) -> tuple[int, int]:
    """The index of the face the 3D view draws at the low end and at the high end of x, found from
    the triangles it was sent: that numbering is what the check's faces have to agree with. A flat
    end that holds the part is either end, so the test compares the two as a set."""
    (part,) = read.shapes["parts"]
    mesh = part["shape"]
    xs: list[float] = []
    first = 0
    for count in mesh["triangles_per_face"]:
        corners = mesh["triangles"][3 * first : 3 * (first + count)]
        xs.append(sum(mesh["vertices"][3 * corner] for corner in corners) / len(corners))
        first += count
    return xs.index(min(xs)), xs.index(max(xs))


def fea_result(card: Scorecard) -> CheckResult:
    (found,) = (one for one in card.finished if one.check_id == "fea")
    return found

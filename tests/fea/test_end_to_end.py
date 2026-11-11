import dataclasses
from pathlib import Path

import pytest
from cases import BEAM_B, BEAM_H, BEAM_L, BEAM_P, STEEL, box, timoshenko_tip
from pydantic import TypeAdapter

from cad.briefs.model import BriefId, BriefSpan, Requirement, RequirementId, Target
from cad.checks import jobs
from cad.checks.container.fea import CLAMPED_FACE_NOTE
from cad.checks.lanes import Lanes
from cad.checks.result import CheckResult, Verdict
from cad.loads.model import LoadCase
from cad.sandbox import host
from cad.sandbox.outcome import Built
from cad.scorecard import requirements, score
from cad.scorecard.model import AgainstBrief, Basis, Checked, Scorecard
from cad.tables.materials import UNITS, Known, MaterialsTable, load_materials, magnitude
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
    lanes = Lanes(jobs.run_job)
    card = score.score_variant(
        built.variant_id,
        KEY,
        tmp_path,
        assess,
        lanes,
        demand=jobs.Demand(loads={case.id: case.wire()}),
    )
    for _ in range(40):
        if not card.pending:
            break
        card = score.score_variant(
            built.variant_id,
            KEY,
            tmp_path,
            assess,
            lanes,
            demand=jobs.Demand(loads={case.id: case.wire()}),
        )
    assert card.pending == ()
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


def fea_result(card: Scorecard) -> CheckResult:
    (found,) = (one for one in card.finished if one.check_id == "fea")
    return found

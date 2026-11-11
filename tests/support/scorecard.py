from typing import Any

from pydantic import TypeAdapter

from cad.briefs.model import BriefId, BriefSpan, Requirement, RequirementId, Target
from cad.checks.report import SPECS, unknown_for_all
from cad.checks.result import CheckResult, Measure, StepMissing, Verdict
from cad.scorecard.material import MaterialUse, ReportedScorecard, SetByAgent
from cad.scorecard.model import (
    Basis,
    Checked,
    NoBrief,
    RequirementResult,
    Scorecard,
)
from cad.tables.materials import UNITS

TARGET = TypeAdapter[Target](Target)
SPEC = {spec.id: spec for spec in SPECS}
BRIEF = BriefId("1" * 16)
UNBUILT_ID = "0123456789abcdef"


def requirement(raw: dict[str, Any], rid: str = "0" * 16) -> Requirement:
    return Requirement(
        id=RequirementId(rid),
        brief_id=BRIEF,
        target=TARGET.validate_python(raw),
        origin=BriefSpan(start=0, end=1),
    )


def quantity(magnitude: float, unit: str) -> dict[str, Any]:
    return {"magnitude": magnitude, "unit": unit}


def max_mass(magnitude: float, unit: str = "g") -> Requirement:
    return requirement({"kind": "max_mass", "mass": quantity(magnitude, unit)})


def min_mass(magnitude: float, unit: str = "g") -> Requirement:
    return requirement({"kind": "min_mass", "mass": quantity(magnitude, unit)})


def envelope(*edges: tuple[float, str]) -> Requirement:
    return requirement({"kind": "envelope", "edges": [quantity(m, u) for m, u in edges]})


def result(check_id: str, verdict: Verdict, **measured: tuple[float, str]) -> CheckResult:
    spec = SPEC[check_id]
    return CheckResult(
        check_id=check_id,
        verdict=verdict,
        measured=tuple(
            Measure(name=name.replace("__", ":"), value=UNITS.Quantity(magnitude, unit))
            for name, (magnitude, unit) in measured.items()
        ),
        formula=spec.formula,
        reason="r",
        sources=spec.sources,
        version=spec.version,
    )


def suite(*replacing: CheckResult) -> tuple[CheckResult, ...]:
    given = {one.check_id: one for one in replacing}
    return tuple(given.get(one.check_id, one) for one in unknown_for_all("not run"))


def weighing(kg: float) -> tuple[CheckResult, ...]:
    return suite(result("mass", Verdict.PASS, volume=(1.0, "mm^3"), mass=(kg, "kg")))


def boxed(smallest: float, middle: float, largest: float) -> tuple[CheckResult, ...]:
    return suite(
        result(
            "extents",
            Verdict.PASS,
            sorted_extent__smallest=(smallest, "mm"),
            sorted_extent__middle=(middle, "mm"),
            sorted_extent__largest=(largest, "mm"),
        )
    )


def checked(judged: RequirementResult) -> Checked:
    assert isinstance(judged, Checked)
    return judged


def offline_card(basis: Basis | None = None) -> Scorecard:
    return Scorecard(
        variant_id=UNBUILT_ID,
        material_key="prusament-pla",
        table_version="t" * 64,
        check_image_digest="sha256:" + "i" * 64,
        brep_sha256="b" * 64,
        step=StepMissing(reason="offline"),
        results=unknown_for_all("offline"),
        basis=NoBrief() if basis is None else basis,
    )


def reported(material_key: str = "prusament-pla") -> ReportedScorecard:
    card = offline_card().model_copy(update={"material_key": material_key})
    return ReportedScorecard(
        **dict(card), material=MaterialUse(key=material_key, set_by=SetByAgent())
    )

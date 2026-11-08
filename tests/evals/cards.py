import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import pint
import pytest
from provenance import (
    CardTrace,
    Stale,
    Unresolved,
    trace_card,
)
from pydantic import TypeAdapter
from trace_store import SPEC_BY_ID

from cad.briefs import store as briefs
from cad.briefs.model import BriefId, Confirmed, Decision, Target
from cad.briefs.store import ConfirmedSet, Draft
from cad.checks.report import SPECS, CheckSpec
from cad.checks.result import CheckResult, Measure, StepStored, Verdict
from cad.scorecard.model import Basis, NoBrief, Scorecard
from cad.scorecard.requirements import against
from cad.scorecard.score import SCORECARD
from cad.tables.materials import UNITS, Cited, MaterialsTable, load_materials

KEY = "prusament-pla"
VARIANT_ID = "0123456789abcdef"
BREP = b"BREP"
STEP = b"STEP"
BREP_SHA = hashlib.sha256(BREP).hexdigest()
STEP_SHA = hashlib.sha256(STEP).hexdigest()


@cache
def table() -> MaterialsTable:
    return load_materials()


def table_number(field: str, unit: str) -> pint.Quantity:
    cited = getattr(table().get_material(KEY), field)
    assert isinstance(cited, Cited)
    return UNITS.Quantity(cited.magnitude_in(unit), unit)


def measures_of(spec: CheckSpec) -> tuple[Measure, ...]:
    return tuple(
        Measure(
            name=name,
            value=table_number(spec.reads[name], unit)
            if name in spec.reads
            else UNITS.Quantity(1.0, unit),
        )
        for name, unit in spec.measures.items()
    )


def genuine_result(spec: CheckSpec) -> CheckResult:
    rows = tuple(getattr(table().get_material(KEY), field).source for field in spec.reads.values())
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict.PASS,
        measured=measures_of(spec),
        formula=spec.formula,
        reason="ok",
        sources=(*spec.sources, *rows),
        version=spec.version,
    )


def genuine_card(**changes: object) -> Scorecard:
    card = Scorecard(
        variant_id=VARIANT_ID,
        material_key=KEY,
        table_version=table().version,
        check_image_digest="sha256:" + "i" * 64,
        brep_sha256=BREP_SHA,
        step=StepStored(sha256=STEP_SHA),
        results=tuple(genuine_result(spec) for spec in SPECS),
        basis=NoBrief(),
    )
    return card.model_copy(update=changes)


def trace(card: Scorecard, root: Path, briefs_root: Path | None = None) -> CardTrace:
    shown = root.parent / "briefs" if briefs_root is None else briefs_root
    return trace_card(card, root, shown, table(), SPEC_BY_ID)


BRIEF_TEXT = "A plate under 150 g that fits in 120 x 80 x 40 mm and looks friendly"
TARGET = TypeAdapter[Target](Target)


def drafts(*rows: tuple[Mapping[str, object], str]) -> list[Draft]:
    return [Draft(target=TARGET.validate_python(raw), quote=quote) for raw, quote in rows]


def confirm(briefs_root: Path, brief_id: str, rows: list[Draft]) -> ConfirmedSet:
    briefs.propose(briefs_root, brief_id, rows)
    state = briefs.read_state(briefs_root, brief_id)
    latest = state.proposals[-1]
    decision = Decision(
        proposal=latest.proposal.number,
        brief_sha256=state.brief_sha256,
        proposal_sha256=latest.sha256,
        answer=Confirmed(),
        decided_at=datetime.now(UTC),
    )
    briefs.record_decision(briefs_root, BriefId(brief_id), decision)
    confirmed = briefs.confirmed_requirements(briefs_root, brief_id)
    assert confirmed is not None
    return confirmed


def judged_card(confirmed: ConfirmedSet) -> Scorecard:
    card = genuine_card()
    basis: Basis = against(confirmed)(card.results)
    return card.model_copy(update={"basis": basis})


def with_result(card: Scorecard, check_id: str, **changes: object) -> Scorecard:
    results = tuple(
        result.model_copy(update=changes) if result.check_id == check_id else result
        for result in card.results
    )
    return card.model_copy(update={"results": results})


def result_of(card: Scorecard, check_id: str) -> CheckResult:
    return next(result for result in card.results if result.check_id == check_id)


def reasons(traced: CardTrace, kind: type[Stale] | type[Unresolved], label: str = "") -> list[str]:
    return [
        one.outcome.reason
        for one in traced.numbers
        if isinstance(one.outcome, kind) and one.label.startswith(label)
    ]


def put(root: Path, card: Scorecard | str) -> None:
    text = card if isinstance(card, str) else card.model_dump_json(indent=2) + "\n"
    (root / VARIANT_ID / SCORECARD).write_text(text)


def lines(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out

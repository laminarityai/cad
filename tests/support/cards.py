import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pint
import pytest
from chain import Stale, Unresolved
from provenance import CardTrace, trace_card
from pydantic import TypeAdapter
from trace_store import SPEC_BY_ID

from cad.briefs import store as briefs
from cad.briefs.model import Confirmed, Decision, Target
from cad.briefs.store import ConfirmedSet, Draft
from cad.checks.report import QUICK, CheckSpec
from cad.checks.result import CheckResult, Measure, StepStored, Verdict
from cad.confirmations import answers
from cad.confirmations.answers import Edit, ItemAnswer, PageAnswer
from cad.records import signed
from cad.records.roots import Roots
from cad.scorecard.model import Basis, NoBrief, Scorecard
from cad.scorecard.requirements import against
from cad.tables.materials import UNITS, Known, MaterialsTable, load_materials

KEY = "prusament-pla"
VARIANT_ID = "0123456789abcdef"
BREP = b"BREP"
STEP = b"STEP"
BREP_SHA = hashlib.sha256(BREP).hexdigest()
STEP_SHA = hashlib.sha256(STEP).hexdigest()


@cache
def table() -> MaterialsTable:
    return load_materials()


def table_number(field: str, unit: str, key: str = KEY) -> pint.Quantity:
    cited = getattr(table().get_material(key), field)
    assert isinstance(cited, Known)
    return UNITS.Quantity(cited.magnitude_in(unit), unit)


def measures_of(spec: CheckSpec, key: str = KEY) -> tuple[Measure, ...]:
    return tuple(
        Measure(
            name=name,
            value=table_number(spec.reads[name], unit, key)
            if name in spec.reads
            else UNITS.Quantity(1.0, unit),
        )
        for name, unit in spec.measures.items()
    )


def genuine_result(spec: CheckSpec, key: str = KEY) -> CheckResult:
    rows = tuple(getattr(table().get_material(key), field).source for field in spec.reads.values())
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict.PASS,
        measured=measures_of(spec, key),
        formula=spec.formula,
        reason="ok",
        sources=(*spec.sources, *rows),
        version=spec.version,
    )


def genuine_card(key: str = KEY, **changes: object) -> Scorecard:
    card = Scorecard(
        variant_id=VARIANT_ID,
        material_key=key,
        table_version=table().version,
        check_image_digest="sha256:" + "i" * 64,
        brep_sha256=BREP_SHA,
        step=StepStored(sha256=STEP_SHA),
        results=tuple(genuine_result(spec, key) for spec in QUICK),
        basis=NoBrief(),
    )
    return card.model_copy(update=changes)


def roots_beside(store: Path) -> Roots:
    return Roots(store.parent / "briefs", store.parent / "projects")


def trace(card: Scorecard, root: Path) -> CardTrace:
    return trace_card(card, root, roots_beside(root), table(), SPEC_BY_ID)


BRIEF_TEXT = "A plate under 150 g that fits in 120 x 80 x 40 mm and looks friendly"
TARGET = TypeAdapter[Target](Target)


def drafts(*rows: tuple[Mapping[str, object], str]) -> list[Draft]:
    return [Draft(target=TARGET.validate_python(raw), quote=quote) for raw, quote in rows]


def confirm(roots: Roots, brief_id: str, rows: list[Draft]) -> ConfirmedSet:
    briefs.propose(roots, brief_id, rows)
    state = briefs.read_state(roots, brief_id)
    latest = state.proposals[-1]
    number = latest.proposal.number
    decision = Decision(
        proposal=number,
        brief_sha256=state.brief_sha256,
        proposal_sha256=latest.sha256,
        answer=Confirmed(),
        decided_at=datetime.now(UTC),
    )
    path = roots.briefs / brief_id / briefs.DECISIONS / signed.slot_file(number)
    record = decision.model_dump_json().encode()
    assert signed.publish(
        signed.Store(roots.briefs, "brief"), f"{brief_id}/decision/{number}", path, record
    )
    return _confirmed(roots, brief_id)


def confirm_on_page(
    roots: Roots, brief_id: str, rows: list[Draft], changes: Mapping[int, str] | None = None
) -> ConfirmedSet:
    briefs.propose(roots, brief_id, rows)
    state = briefs.read_state(roots, brief_id)
    project = state.brief.project
    proposed = state.proposals[-1]
    edits = tuple(
        Edit(row=proposed.proposal.requirements[index].id, text=text)
        for index, text in (changes or {}).items()
    )
    item = ItemAnswer(item=proposed.ref, verdict="confirmed", edits=edits)
    page = PageAnswer(project=project, answers=(item,), decided_at=datetime.now(UTC))
    assert answers.append_answer(roots.projects, project, page)
    return _confirmed(roots, brief_id)


def _confirmed(roots: Roots, brief_id: str) -> ConfirmedSet:
    confirmed = briefs.confirmed_requirements(roots, brief_id)
    assert confirmed is not None
    return confirmed


def judged_card(confirmed: ConfirmedSet) -> Scorecard:
    card = genuine_card()
    basis: Basis = against(confirmed)(card.finished)
    return card.model_copy(update={"basis": basis})


def with_result(card: Scorecard, check_id: str, **changes: object) -> Scorecard:
    results = tuple(
        result.model_copy(update=changes) if result.check_id == check_id else result
        for result in card.results
    )
    return card.model_copy(update={"results": results})


def result_of(card: Scorecard, check_id: str) -> CheckResult:
    return next(result for result in card.finished if result.check_id == check_id)


def reasons(traced: CardTrace, kind: type[Stale] | type[Unresolved], label: str = "") -> list[str]:
    return [
        one.outcome.reason
        for one in traced.numbers
        if isinstance(one.outcome, kind) and one.label.startswith(label)
    ]


def transcript_of(root: Path) -> Path:
    return root.parent / "transcript.json"


def write_transcript(root: Path, *cards: Scorecard | str) -> None:
    """Write the transcript of a session whose scorecard calls returned `cards`, in order."""
    events: list[dict[str, Any]] = []
    for number, card in enumerate(cards):
        text = card if isinstance(card, str) else card.model_dump_json(indent=2)
        call = f"call-{number}"
        use: dict[str, Any] = {
            "type": "tool_use",
            "id": call,
            "name": "mcp__cad__score_variant",
            "input": {},
        }
        result = {
            "type": "tool_result",
            "tool_use_id": call,
            "content": [{"type": "text", "text": text}],
        }
        events += [
            {"type": "assistant", "message": {"content": [use]}},
            {"type": "user", "message": {"content": [result]}},
        ]
    transcript_of(root).write_text(json.dumps(events))


def lines(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out

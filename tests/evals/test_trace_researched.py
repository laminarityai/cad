import json
from datetime import date
from pathlib import Path

import pytest
from chain import BoundStep, ResearchedStep, Resolved
from mcp import Client
from provenance import CardTrace, trace_card
from trace_store import SPEC_BY_ID, main

from cad.briefs import store as briefs
from cad.briefs.model import Brief
from cad.checks.result import CheckResult, Measure, ReadCited, ReadResearched, Verdict
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.research.fetch import Page
from cad.research.overlay import project_table
from cad.research.requests import request_for
from cad.research.submit import Question, ResearchAccepted, submit
from cad.scorecard import material
from cad.scorecard.model import AwaitingConfirmation
from cad.server.app import build_server
from cad.tables.materials import UNITS, Known, MaterialsTable
from tests.support.cards import (
    BRIEF_TEXT,
    genuine_card,
    lines,
    roots_beside,
    table,
    transcript_of,
    write_transcript,
)

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
URL = "https://example.org/pla"
KEY = "prusament-petg"
QUOTE = "Poisson's ratio 0.36"


def arguments_for(store: Path) -> list[str]:
    roots = roots_beside(store)
    return [
        str(transcript_of(store)),
        "--root",
        str(store),
        "--briefs-root",
        str(roots.briefs),
        "--projects-root",
        str(roots.projects),
    ]


@pytest.mark.anyio
@pytest.mark.docker
async def test_a_card_the_server_returned_through_score_variant_traces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "store"
    store.mkdir()
    async with Client(build_server(store, roots_beside(store))) as client:
        built = await client.call_tool("build_variant", {"code": PLATE})
        assert built.structured_content is not None
        scored = await client.call_tool(
            "score_variant",
            {"variant_id": built.structured_content["variant_id"], "material_key": KEY},
        )
    write_transcript(store, json.dumps(scored.structured_content))
    assert main(arguments_for(store)) == 0
    assert "cards unreadable: 0, unbound: 0, incomplete: 0" in lines(capsys)


def research(roots: Roots, brief: Brief, key: str) -> None:
    question = Question(brief.id, brief.project, key, "poisson_ratio", 0.36, "", URL, QUOTE)
    page = Page(URL, "PLA data", f"Mechanical properties {QUOTE} Density 1.24 g/cm3", "ab" * 32)
    answer = submit(
        table(), roots.projects, question, fetcher=lambda _: page, today=lambda: date(2026, 11, 8)
    )
    assert isinstance(answer, ResearchAccepted)


def researched(roots: Roots) -> tuple[str, MaterialsTable]:
    brief = briefs.create_brief(roots, BRIEF_TEXT, new_project_id())
    research(roots, brief, KEY)
    return brief.id, project_table(table(), roots.projects, brief.project).table


def fea_result(scored: MaterialsTable) -> CheckResult:
    spec = SPEC_BY_ID["fea"]
    row = scored.get_material(KEY)
    held = {field: row.value(field) for field in spec.reads.values()}
    measured: list[Measure] = []
    for name, unit in spec.measures.items():
        value = held[spec.reads[name]] if name in spec.reads else None
        magnitude = value.magnitude_in(unit) if isinstance(value, Known) else 1.0
        measured.append(Measure(name=name, value=UNITS.Quantity(magnitude, unit)))
    sources = tuple(value.source for value in held.values() if isinstance(value, Known))
    return CheckResult(
        check_id=spec.id,
        verdict=Verdict.PASS,
        measured=tuple(measured),
        formula=spec.formula,
        reason="ok",
        sources=(*spec.sources, *sources),
        version=spec.version,
        reads=(
            ReadCited(field="elastic_modulus"),
            ReadResearched(field="poisson_ratio", url=URL, quote=QUOTE, sha256="ab" * 32),
            ReadCited(field="yield_strength"),
        ),
    )


def stored_researched_card(store: Path) -> tuple[material.ReportedScorecard, MaterialsTable]:
    roots = roots_beside(store)
    brief_id, scored = researched(roots)
    card = genuine_card(
        KEY,
        table_version=scored.version,
        results=(*genuine_card(KEY).results, fea_result(scored)),
        basis=AwaitingConfirmation(brief_id=brief_id),
    )
    reported = material.reported(card, None)
    write_transcript(store, reported)
    return reported, scored


def traced(card: material.ReportedScorecard, store: Path, scored: MaterialsTable) -> CardTrace:
    return trace_card(card, store, roots_beside(store), scored, SPEC_BY_ID)


def test_a_stored_card_that_read_a_researched_value_traces_it_to_the_record(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card, scored = stored_researched_card(store)
    poisson = next(
        one for one in traced(card, store, scored).numbers if one.label.endswith("son_ratio")
    )
    assert isinstance(poisson.outcome, Resolved)
    step = poisson.outcome.steps[-1]
    assert isinstance(step, ResearchedStep)
    assert (step.field, step.record, step.source.quote) == ("poisson_ratio", 1, QUOTE)
    main([*arguments_for(store), "--steps"])
    out = lines(capsys)
    assert "cards unreadable: 0" in out
    assert f"researched {KEY}.poisson_ratio, record 1, {URL}" in out
    assert "stale: 0, unresolved: 0" in out


def test_the_bounds_of_a_research_request_on_a_stored_card_resolve(store: Path) -> None:
    card, scored = stored_researched_card(store)
    asking = card.model_copy(update={"research": (request_for(None, KEY, "yield_strength"),)})
    bounds = [
        one for one in traced(asking, store, scored).numbers if one.label.startswith("research")
    ]
    assert [type(one.outcome) for one in bounds] == [Resolved, Resolved]
    assert all(
        isinstance(one.outcome, Resolved) and isinstance(one.outcome.steps[0], BoundStep)
        for one in bounds
    )


def test_a_record_for_a_value_the_card_never_read_leaves_the_card_current(
    store: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    card, _ = stored_researched_card(store)
    roots = roots_beside(store)
    assert isinstance(card.basis, AwaitingConfirmation)
    research(roots, briefs.read_brief(roots, card.basis.brief_id), "bambu-pla-basic")
    main(arguments_for(store))
    assert "stale: 0, unresolved: 0" in lines(capsys)

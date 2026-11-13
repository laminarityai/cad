"""A session that scores, researches the value a check could not read, and scores again was shown
two honest cards. Each rests on its own signed job, which the server keys by the card's own
material and table version, so both trace. A card that shows one job's values under the other
job's table version is untraced."""

from datetime import date
from pathlib import Path

from tracefacts import trace_session

from cad.briefs import store as briefs
from cad.checks.report import QUICK
from cad.checks.result import CheckResult, Measure, Verdict
from cad.operations.research import brief_table
from cad.records.roots import Roots
from cad.research.fetch import Page
from cad.research.submit import Question, ResearchAccepted, submit
from cad.scorecard.model import AwaitingConfirmation
from cad.tables.materials import UNITS, Known, MaterialsTable
from tests.support.cards import (
    confirm_on_page,
    drafts,
    genuine_card,
    genuine_result,
    table,
    transcript_of,
    write_transcript,
)
from tests.support.readings import a_session, built, reading_of, store_quick

PROJECT = "project-mystery-resin"
URL = "https://example.org/resin"
QUOTE = "Density 1.20 g/cm3"
LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")
MASS = next(spec for spec in QUICK if spec.id == "mass")
GEOMETRY = (
    Measure(name="volume", value=UNITS.Quantity(1000.0, "mm^3")),
    *(Measure(name=f"center_of_mass:{axis}", value=UNITS.Quantity(0.0, "mm")) for axis in "xyz"),
)


def quick_with(mass: CheckResult) -> tuple[CheckResult, ...]:
    return tuple(mass if spec.id == MASS.id else genuine_result(spec) for spec in QUICK)


def unknown_mass() -> CheckResult:
    return CheckResult(
        check_id=MASS.id,
        verdict=Verdict.UNKNOWN,
        measured=GEOMETRY,
        formula=MASS.formula,
        reason=f"the materials table has no density for {PROJECT}",
        sources=MASS.sources,
        version=MASS.version,
    )


def mass_on(researched: MaterialsTable) -> CheckResult:
    density = researched.get_material(PROJECT).density
    assert isinstance(density, Known)
    per_mm3 = density.magnitude_in("kg/mm^3")
    return CheckResult(
        check_id=MASS.id,
        verdict=Verdict.PASS,
        measured=(
            *GEOMETRY,
            Measure(name="density", value=UNITS.Quantity(per_mm3, "kg/mm^3")),
            Measure(name="mass", value=UNITS.Quantity(1000.0 * per_mm3, "kg")),
        ),
        formula=MASS.formula,
        reason="ok",
        sources=(*MASS.sources, density.source),
        version=MASS.version,
    )


def research_density(roots: Roots, brief_id: str) -> MaterialsTable:
    unresearched = brief_table(roots, brief_id).table
    held = briefs.read_brief(roots, brief_id)
    question = Question(held.id, held.project, PROJECT, "density", 1.2, "g/cm^3", URL, QUOTE)
    page = Page(URL, "Resin", f"Properties {QUOTE} and more", "ab" * 32)
    answer = submit(
        table(), roots.projects, question, fetcher=lambda _: page, today=lambda: date(2026, 11, 13)
    )
    assert isinstance(answer, ResearchAccepted), answer
    researched = brief_table(roots, brief_id).table
    assert researched.version != unresearched.version
    return researched


def rescored(tmp_path: Path) -> tuple[Path, Path, Roots, str, str]:
    """A session shown the server's card before and after research, then confirmed: the home,
    the variant store, the roots, and the two cards."""
    home, variants, roots, brief_id = a_session(tmp_path)
    held = built(variants)
    asked = genuine_card(
        variant_id=held.id,
        material_key=PROJECT,
        basis=AwaitingConfirmation(brief_id=brief_id),
    )
    unresearched = brief_table(roots, brief_id).table
    store_quick(variants, held, quick_with(unknown_mass()), PROJECT, unresearched)
    before = reading_of(home, asked)
    researched = research_density(roots, brief_id)
    store_quick(variants, held, quick_with(mass_on(researched)), PROJECT, researched)
    after = reading_of(home, asked)
    confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))
    return home, variants, roots, before, after


def test_a_card_scored_before_research_traces_beside_the_card_scored_after(
    tmp_path: Path,
) -> None:
    home, variants, _, before, after = rescored(tmp_path)
    write_transcript(variants, before, after)
    traced = trace_session(home, transcript_of(variants))
    assert traced.traced, traced.untraced
    assert traced.shown.cards == 2
    assert traced.shown.numbers == traced.shown.resolved > 0

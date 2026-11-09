from datetime import date
from pathlib import Path

import pytest

from cad.briefs.store import create_brief
from cad.projects.model import ProjectId, new_project_id
from cad.records.roots import Roots
from cad.research.fetch import FetchFailed, Page
from cad.research.fields import SPECS, Field
from cad.research.ledger import Ledger, read_ledger
from cad.research.overlay import overlay, project_table
from cad.research.submit import (
    Fetch,
    Question,
    ResearchAccepted,
    ResearchRefused,
    submit,
)
from cad.tables.materials import (
    FromResearch,
    Known,
    Material,
    MaterialsTable,
    Unknown,
    load_materials,
)

URL = "https://example.org/pla"
TEXT = "Mechanical properties Density 1.24 g/cm3 Poisson's ratio 0.36 Tensile strength 50 MPa"
GIT = load_materials()


def page(text: str = TEXT, url: str = URL) -> Fetch:
    return lambda asked: Page(url, "PLA data", text, "ab" * 32)


@pytest.fixture
def roots(tmp_path: Path) -> Roots:
    return Roots(tmp_path / "briefs", tmp_path / "projects")


def ask(
    roots: Roots,
    quote: str = "Poisson's ratio 0.36",
    *,
    value: float = 0.36,
    unit: str = "",
    key: str = "prusament-pla",
    field: Field = "poisson_ratio",
    fetcher: Fetch | None = None,
    project: ProjectId | None = None,
) -> ResearchAccepted | ResearchRefused:
    pid = project or create_brief(roots, "a bracket", new_project_id()).project
    question = Question("b-1", pid, key, field, value, unit, URL, quote)
    return submit(
        GIT, roots.projects, question, fetcher=fetcher or page(), today=lambda: date(2026, 11, 8)
    )


def table_of(roots: Roots, project: ProjectId) -> MaterialsTable:
    return project_table(GIT, roots.projects, project).table


def test_a_quote_on_the_page_fills_the_unknown_field_for_that_project_only(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    other = create_brief(roots, "a shelf", new_project_id()).project
    answer = ask(roots, project=pid)
    assert isinstance(answer, ResearchAccepted)
    assert (answer.value, answer.record) == (0.36, 1)
    filled = table_of(roots, pid)
    value = filled.get_material("prusament-pla").poisson_ratio
    assert isinstance(value, Known)
    assert value.basis == FromResearch("ab" * 32, 1)
    assert (value.source.url, value.source.quote) == (URL, "Poisson's ratio 0.36")
    assert filled.version == f"{GIT.version}+{pid}@r1"
    assert isinstance(table_of(roots, other).get_material("prusament-pla").poisson_ratio, Unknown)
    assert table_of(roots, other).version == GIT.version


def test_a_quote_not_on_the_page_is_refused_with_a_new_request(roots: Roots) -> None:
    answer = ask(roots, "Poisson's ratio 0.30", value=0.3)
    assert isinstance(answer, ResearchRefused)
    assert "does not appear on" in answer.reason
    assert answer.request is not None
    assert answer.request.field == "poisson_ratio"
    assert answer.request.problems == (answer.reason,)


def test_a_quote_not_on_the_page_is_refused_with_where_the_page_writes_the_value(
    roots: Roots,
) -> None:
    text = "Young's modulus E 2-2.6 GPa Poisson's ratio \u03bd 0.38 Yield strength 35 MPa"
    answer = ask(roots, "Poisson's ratio 0.38", value=0.38, fetcher=page(text))
    assert isinstance(answer, ResearchRefused)
    assert "the page writes 0.38 here" in answer.reason
    assert "poisson's ratio \u03bd 0.38" in answer.reason


def test_whitespace_and_apostrophe_style_do_not_hide_a_quote(roots: Roots) -> None:
    answer = ask(roots, "Poisson\u2019s   ratio\n0.36")
    assert isinstance(answer, ResearchAccepted)


def test_a_failed_fetch_is_a_reason_and_a_new_request(roots: Roots) -> None:
    answer = ask(roots, fetcher=lambda url: FetchFailed("the host x resolves to 10.0.0.1"))
    assert isinstance(answer, ResearchRefused)
    assert answer.reason == "the host x resolves to 10.0.0.1"
    assert answer.request is not None


ARTICLE = (
    "Material properties. For the simulation, the Poisson ratio = 0.36, was used, as reported "
    "for PLA. Density 1.21 g/cm\u00b3 was measured by pycnometry. "
    "Property | Value | Unit Tensile modulus | 3,5 | GPa Yield strength | 1.24e3 | psi"
)


@pytest.mark.parametrize(
    ("quote", "field", "value", "unit", "canonical"),
    [
        ("the Poisson ratio = 0.36, was used", "poisson_ratio", 0.36, "", 0.36),
        ("Density 1.21 g/cm\u00b3", "density", 1.21, "g/cm\u00b3", 1210.0),
        ("Tensile modulus | 3,5 | GPa", "elastic_modulus", 3.5, "GPa", 3500.0),
        ("Yield strength | 1.24e3 | psi", "yield_strength", 1240, "psi", 8.54949868),
    ],
)
def test_the_agents_reading_of_an_ordinary_quote_is_accepted_in_the_canonical_unit(
    roots: Roots, quote: str, field: Field, value: float, unit: str, canonical: float
) -> None:
    blank = Material("blank", "Blank", *(Unknown() for _ in range(5)))
    table = MaterialsTable(GIT.version, {**GIT.materials, "blank": blank})
    pid = create_brief(roots, "a bracket", new_project_id()).project
    question = Question("b-1", pid, "blank", field, value, unit, URL, quote)
    answer = submit(table, roots.projects, question, fetcher=page(ARTICLE))
    assert isinstance(answer, ResearchAccepted), answer
    assert answer.value == pytest.approx(canonical)
    assert (answer.unit, answer.url, answer.quote) == (SPECS[field].canonical_unit, URL, quote)


def test_a_value_not_written_in_the_quote_is_refused_before_the_fetch(roots: Roots) -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> Page:
        fetched.append(url)
        return Page(url, "PLA", TEXT, "ab" * 32)

    answer = ask(roots, value=0.35, fetcher=fetcher)
    assert isinstance(answer, ResearchRefused)
    assert "0.35 is not written in the quote" in answer.reason
    assert answer.request is not None
    assert fetched == []


def test_a_value_converted_from_the_quote_is_not_written_in_it(roots: Roots) -> None:
    answer = ask(
        roots,
        "Yield strength 4.35 ksi",
        value=30,
        unit="MPa",
        field="yield_strength",
        key="bambu-pla-basic",
    )
    assert isinstance(answer, ResearchRefused)
    assert "not written in the quote" in answer.reason


def test_a_unit_the_server_has_no_key_for_is_refused_with_the_spellings_it_takes(
    roots: Roots,
) -> None:
    answer = ask(
        roots,
        "Yield strength 30 MPa",
        value=30,
        unit="megapascal",
        field="yield_strength",
        key="bambu-pla-basic",
    )
    assert isinstance(answer, ResearchRefused)
    assert "'megapascal' is not one the server converts" in answer.reason
    assert "'MPa'" in answer.reason


def test_a_cited_value_is_never_replaced(roots: Roots) -> None:
    answer = ask(roots, "Density 1.24 g/cm3", value=1.24, unit="g/cm3", field="density")
    assert isinstance(answer, ResearchRefused)
    assert "already has a cited density" in answer.reason
    assert answer.request is None


def test_a_key_with_no_row_asks_for_nothing(roots: Roots) -> None:
    answer = ask(roots, key="unobtainium")
    assert isinstance(answer, ResearchRefused)
    assert answer.request is None


def test_the_same_answer_twice_stores_one_record(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    first, second = ask(roots, project=pid), ask(roots, project=pid)
    assert first == second
    assert len(read_ledger(roots.projects, pid).records) == 1


def test_a_researched_value_is_never_replaced_by_another_reading(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    assert isinstance(ask(roots, project=pid), ResearchAccepted)
    text = "Poisson's ratio 0.36. Poisson's ratio 0.4"
    again = ask(roots, "Poisson's ratio 0.4", value=0.4, project=pid, fetcher=page(text))
    assert isinstance(again, ResearchRefused)
    assert "already has a researched poisson_ratio" in again.reason
    assert again.request is None
    held = table_of(roots, pid).get_material("prusament-pla").poisson_ratio
    assert isinstance(held, Known)
    assert held.magnitude_in("dimensionless") == 0.36


def test_a_value_that_breaks_the_table_rules_is_refused(roots: Roots) -> None:
    text = "Yield strength 90 MPa"
    answer = ask(
        roots,
        text,
        value=90,
        unit="MPa",
        field="yield_strength",
        key="bambu-pla-basic",
        fetcher=page(text),
    )
    assert isinstance(answer, ResearchRefused)
    assert "breaks the table's rules" in answer.reason
    assert "above tensile_strength" in answer.reason


def test_a_record_git_now_cites_is_dropped_and_the_table_still_loads(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    assert isinstance(ask(roots, project=pid), ResearchAccepted)
    records = read_ledger(roots.projects, pid).records
    stale = records[0].model_copy(
        update={"field": "density", "magnitude": 1240.0, "unit": "kg/m^3"}
    )
    reloaded = overlay(GIT, pid, Ledger((*records, stale)))
    assert [one.number for one in reloaded.dropped] == [2]
    assert "never replaces" in reloaded.dropped[0].problems[0]
    assert reloaded.table.version.endswith("@r2")


def test_a_ledger_the_store_did_not_sign_gives_no_values_and_says_why(roots: Roots) -> None:
    pid = unreadable(roots)
    ledger = read_ledger(roots.projects, pid)
    assert ledger.records == ()
    assert ledger.problem is not None
    loaded = project_table(GIT, roots.projects, pid)
    assert loaded.table.version == GIT.version
    assert loaded.problem == ledger.problem


def test_a_quote_cut_from_a_longer_number_is_refused(roots: Roots) -> None:
    answer = ask(roots, "Poisson's ratio 0.3", value=0.3, fetcher=page("Poisson's ratio 0.35"))
    assert isinstance(answer, ResearchRefused)
    assert "does not appear on" in answer.reason


@pytest.mark.parametrize("value", ["0", "0.5"])
def test_a_poisson_ratio_the_table_rules_refuse_is_refused_before_the_fetch(
    roots: Roots, value: str
) -> None:
    fetched: list[str] = []

    def fetcher(url: str) -> Page:
        fetched.append(url)
        return Page(url, "PLA", f"Poisson's ratio {value}", "ab" * 32)

    answer = ask(roots, f"Poisson's ratio {value}", value=float(value), fetcher=fetcher)
    assert isinstance(answer, ResearchRefused)
    assert "more than 0 and less than 0.5" in answer.reason
    assert fetched == []


def unreadable(roots: Roots) -> ProjectId:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    assert isinstance(ask(roots, project=pid), ResearchAccepted)
    record = next((roots.projects / pid / "research").glob("*.signed"))
    record.write_bytes(record.read_bytes().replace(b"0.36", b"0.46"))
    return pid


def test_an_unreadable_ledger_is_refused_before_the_fetch_and_asks_for_nothing(
    roots: Roots,
) -> None:
    pid = unreadable(roots)
    fetched: list[str] = []

    def fetcher(url: str) -> Page:
        fetched.append(url)
        return Page(url, "PLA", TEXT, "ab" * 32)

    answer = ask(roots, project=pid, fetcher=fetcher)
    assert isinstance(answer, ResearchRefused)
    assert answer.reason == read_ledger(roots.projects, pid).problem
    assert answer.request is None
    assert fetched == []

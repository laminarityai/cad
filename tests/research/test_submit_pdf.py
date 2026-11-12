from datetime import date

from cad.briefs.store import create_brief
from cad.projects.model import ProjectId, new_project_id
from cad.records.roots import Roots
from cad.research.fetch import Page, PdfText
from cad.research.overlay import project_table
from cad.research.submit import Fetch, Question, ResearchAccepted, ResearchRefused, submit
from cad.tables.materials import FromResearch, Known, load_materials

URL = "https://example.org/petg-tds.pdf"
GIT = load_materials()
# Page 2 as PDFium reads a datasheet table: each column comes as its own run of lines.
PAGES = (
    "PETG technical data sheet\nPrinting guide",
    "PROPERTY\nTEST METHOD\nVALUE\nDensity\nPoisson's ratio\nISO 1183\nISO 527\n1.27 g/cm3\n0.38",
)


def pdf(pages: tuple[str, ...] = PAGES, url: str = URL) -> Fetch:
    return lambda asked: PdfText(url, "PETG TDS", pages, "cd" * 32)


def ask(
    roots: Roots, quote: str, value: float, fetcher: Fetch, project: ProjectId | None = None
) -> ResearchAccepted | ResearchRefused:
    pid = project or create_brief(roots, "a bracket", new_project_id()).project
    question = Question("b-1", pid, "prusament-petg", "poisson_ratio", value, "", URL, quote)
    return submit(GIT, roots.projects, question, fetcher=fetcher, today=lambda: date(2026, 11, 11))


def test_a_quote_on_a_pdf_page_is_cited_at_that_page(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    answer = ask(roots, "ISO 527 1.27 g/cm3 0.38", 0.38, pdf(), pid)
    assert isinstance(answer, ResearchAccepted)
    assert (answer.value, answer.page, answer.url) == (0.38, 2, URL)
    table = project_table(GIT, roots.projects, pid).table
    value = table.get_material("prusament-petg").poisson_ratio
    assert isinstance(value, Known)
    assert value.basis == FromResearch("cd" * 32, 1)
    assert value.source.url == f"{URL}#page=2"
    assert value.source.page == "page 2 of the PDF the server fetched"


def test_the_same_pdf_answer_twice_is_the_same_record(roots: Roots) -> None:
    pid = create_brief(roots, "a bracket", new_project_id()).project
    first = ask(roots, "ISO 527 1.27 g/cm3 0.38", 0.38, pdf(), pid)
    again = ask(roots, "ISO 527 1.27 g/cm3 0.38", 0.38, pdf(), pid)
    assert isinstance(first, ResearchAccepted)
    assert again == first


def test_a_quote_split_across_two_pdf_pages_is_not_on_either(roots: Roots) -> None:
    answer = ask(roots, "Printing guide PROPERTY TEST METHOD VALUE 0.38", 0.38, pdf())
    assert isinstance(answer, ResearchRefused)
    assert "does not appear on" in answer.reason


def test_a_wrong_number_in_a_pdf_quote_is_refused_with_where_the_pdf_writes_it(
    roots: Roots,
) -> None:
    answer = ask(roots, "ISO 527 1.27 g/cm3 0.36", 0.36, pdf())
    assert isinstance(answer, ResearchRefused)
    assert "does not appear on" in answer.reason
    assert "does not write 0.36 anywhere" in answer.reason
    seen = ask(roots, "Poisson's ratio 0.38", 0.38, pdf())
    assert isinstance(seen, ResearchRefused)
    assert "the page writes 0.38 here" in seen.reason


def test_a_web_page_answer_names_no_pdf_page(roots: Roots) -> None:
    answer = ask(
        roots,
        "Poisson's ratio 0.38",
        0.38,
        lambda asked: Page(URL, "PETG", "Poisson's ratio 0.38", "ab" * 32),
    )
    assert isinstance(answer, ResearchAccepted)
    assert answer.page is None

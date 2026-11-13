from datetime import date

from cad.checks.report import DEPENDENCIES, SPECS, build_request, reads_of
from cad.checks.result import ReadCited, ReadMissing, ReadResearched, StepStored, Verdict
from cad.operations.research import with_research
from cad.projects.model import ProjectId
from cad.research.ledger import Ledger, ResearchedRecord
from cad.research.overlay import ProjectTable, overlay
from cad.research.requests import requests_on
from cad.scorecard import material, requirements
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import Checked, NoBrief, PendingCheck, Scorecard
from cad.tables.fields import Printed
from cad.tables.materials import MaterialsTable, load_materials
from tests.support.scorecard import max_mass, result

GIT = load_materials()
FEA = next(spec for spec in SPECS if spec.id == "fea")
URL = "https://example.org/pla"
QUOTE = "Poisson's ratio 0.36"


def researched(key: str = "prusament-petg") -> MaterialsTable:
    record = ResearchedRecord(
        project="p-1",
        key=key,
        field="poisson_ratio",
        magnitude=0.36,
        unit="dimensionless",
        url=URL,
        title="PLA",
        quote=QUOTE,
        retrieved=date(2026, 11, 8),
        sha256="ab" * 32,
    )
    return overlay(GIT, ProjectId("p-1"), Ledger((record,))).table


def pending(table: MaterialsTable, key: str = "prusament-petg") -> PendingCheck:
    reads = reads_of(FEA, build_request(key, table, (FEA,)))
    return PendingCheck(
        check_id="fea", formula=FEA.formula, sources=FEA.sources, version=FEA.version, reads=reads
    )


def test_a_missing_material_value_on_a_pending_fea_asks_for_research() -> None:
    card = pending(GIT)
    assert card.reads[1] == ReadMissing(
        field="poisson_ratio",
        reason="the materials table has no poisson_ratio for prusament-petg: it says unknown",
    )
    [request] = requests_on([card], "prusament-petg", GIT, "b-1")
    assert (request.brief_id, request.key, request.field) == (
        "b-1",
        "prusament-petg",
        "poisson_ratio",
    )
    assert (request.unit, request.low, request.high) == ("dimensionless", 0.0, 0.5)
    assert request.exclusive
    assert "more than 0 and less than 0.5" in request.instruction
    assert "submit_research" in request.instruction
    assert "the value is written in the quote" in request.instruction


def test_a_researched_value_is_read_with_its_source_and_asks_for_nothing() -> None:
    table = researched()
    card = pending(table)
    assert card.reads == (
        ReadCited(field="elastic_modulus"),
        ReadResearched(field="poisson_ratio", url=URL, quote=QUOTE, sha256="ab" * 32),
        ReadCited(field="yield_strength", specimen=Printed("X-Y")),
    )
    assert requests_on([card], "prusament-petg", table, "b-1") == ()


def test_without_a_brief_the_request_says_to_score_with_one() -> None:
    [request] = requests_on([pending(GIT)], "prusament-petg", GIT, None)
    assert request.brief_id is None
    assert request.instruction.startswith("Score the variant again with a brief_id first")


def test_a_key_with_no_row_asks_for_nothing() -> None:
    assert requests_on([pending(GIT, "unobtainium")], "unobtainium", GIT, "b-1") == ()


def test_a_requirement_decided_on_a_researched_value_says_so_and_names_it() -> None:
    read = ReadResearched(field="density", url=URL, quote="Density 1.24 g/cm3", sha256="cd" * 32)
    weighed = result("mass", Verdict.PASS, volume=(1.0, "mm^3"), mass=(0.1, "kg"))
    weighed = weighed.model_copy(update={"reads": (read,)})
    judged = requirements.judge(max_mass(150), [weighed])
    assert isinstance(judged, Checked)
    assert (judged.verdict, judged.basis, judged.researched) == (
        Verdict.PASS,
        "researched",
        (read,),
    )


def test_a_requirement_on_cited_values_has_the_checks_basis() -> None:
    weighed = result("mass", Verdict.PASS, volume=(1.0, "mm^3"), mass=(0.1, "kg"))
    weighed = weighed.model_copy(update={"reads": (ReadCited(field="density"),)})
    judged = requirements.judge(max_mass(150), [weighed])
    assert isinstance(judged, Checked)
    assert (judged.basis, judged.researched) == ("checks", ())


def test_the_research_code_stays_out_of_every_check_version() -> None:
    assert not [path for path in DEPENDENCIES.files if path.startswith("cad/research/")]


def card_asking() -> ReportedScorecard:
    card = Scorecard(
        variant_id="0123456789abcdef",
        material_key="prusament-petg",
        table_version=GIT.version,
        check_image_digest="sha256:" + "i" * 64,
        brep_sha256="b" * 64,
        step=StepStored(sha256="s" * 64),
        results=(pending(GIT),),
        pending=("fea",),
        basis=NoBrief(),
    )
    return material.reported(card, None)


def test_a_readable_project_gets_a_research_request() -> None:
    card = with_research(card_asking(), ProjectTable(GIT), "b-1")
    assert [one.field for one in card.research] == ["poisson_ratio"]
    assert card.research_problem is None


def test_an_unreadable_ledger_puts_its_problem_on_the_card_and_asks_for_nothing() -> None:
    problem = "project p-1's research records cannot be read"
    card = with_research(card_asking(), ProjectTable(GIT, problem=problem), "b-1")
    assert card.research == ()
    assert card.research_problem == problem


def test_a_project_key_with_no_row_asks_for_every_value_the_check_read() -> None:
    key = "project-acme-silk-pla"
    card = pending(GIT, key)
    assert all(isinstance(read, ReadMissing) for read in card.reads)
    requests = requests_on([card], key, GIT, "b-1")
    assert [(one.key, one.field) for one in requests] == [
        (key, "elastic_modulus"),
        (key, "poisson_ratio"),
        (key, "yield_strength"),
    ]

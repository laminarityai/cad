"""write_check end to end without a container: the blind, form, units and worked-example gates,
and the signed store. Each refusal stores nothing."""

from datetime import date
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from cad.agent_checks import store
from cad.agent_checks.model import SourceInput
from cad.agent_checks.store import CheckRefused, StoredCheck
from cad.agent_checks.write import write_check
from cad.briefs import store as briefs
from cad.briefs.model import BriefId, Target
from cad.briefs.store import Draft
from cad.projects.model import ProjectId, new_project_id
from cad.records.roots import Roots
from cad.research.fetch import Page, PdfText
from cad.research.submit import Fetch
from cad.variant_sets import store as sets
from cad.variant_sets.model import SetKey
from cad.variants.entry import VariantId
from tests.support.agent_checks import (
    EXAMPLE_QUOTE,
    GUIDE,
    GUIDE_TEXT,
    fetching,
    snap_fit,
    unchecked_brief,
)

pytestmark = pytest.mark.usefixtures("no_sandbox")


def project_of(roots: Roots, brief_id: str) -> ProjectId:
    return briefs.read_brief(roots, brief_id).project


def build_a_variant(roots: Roots, brief_id: str) -> None:
    key = SetKey(project_of(roots, brief_id), BriefId(brief_id))
    sets.join(roots.projects, key, "part = Box(20, 5, 2)", VariantId("4" * 16))


def write(roots: Roots, *, fetcher: Fetch | None = None, **changes: Any) -> StoredCheck:
    brief_id, requirement_id = unchecked_brief(roots)
    return write_check(
        roots,
        brief_id,
        requirement_id,
        snap_fit(**changes),
        fetcher=fetcher or fetching(),
        today=lambda: date(2026, 11, 12),
    )


def refused(roots: Roots, **changes: Any) -> str:
    with pytest.raises(CheckRefused) as error:
        write(roots, **changes)
    assert "Nothing was stored" in str(error.value)
    assert not list(roots.projects.glob("*/agent_checks/*.signed"))
    return str(error.value)


def test_a_check_is_frozen_signed_and_named_by_its_sha256(roots: Roots) -> None:
    stored = write(roots)
    check = stored.check
    assert stored.number == 1
    assert store.checks_of(roots.projects, ProjectId(check.project)) == (stored,)
    assert store.find(roots.projects, ProjectId(check.project), stored.sha256) == stored
    assert check.words == "at most 2% strain"
    assert check.source == "your words"
    assert check.example.computed == pytest.approx(0.75)
    assert check.example.cited.url == GUIDE
    assert check.sources[0].cited.retrieved == date(2026, 11, 12)
    assert [one.binding for one in check.inputs if one.name == "k"] == [SourceInput(name="k")]


def test_a_requirement_quoted_from_a_file_gets_a_check_with_the_files_words(roots: Roots) -> None:
    brief_id, requirement_id = unchecked_brief(roots, from_a_file=True)
    stored = write_check(roots, brief_id, requirement_id, snap_fit(), fetcher=fetching())
    assert (stored.check.source, stored.check.words) == ("catch.pdf", "at most 2% strain")


def test_attack_a_check_written_after_a_variant_exists_is_refused(roots: Roots) -> None:
    brief_id, requirement_id = unchecked_brief(roots)
    build_a_variant(roots, brief_id)
    with pytest.raises(CheckRefused, match="only before any variant of its brief exists"):
        write_check(roots, brief_id, requirement_id, snap_fit(), fetcher=fetching())


def test_attack_a_variant_built_while_the_pages_are_fetched_refuses_the_freeze(
    roots: Roots,
) -> None:
    brief_id, requirement_id = unchecked_brief(roots)

    def build_then_fetch(url: str) -> Page | PdfText:
        build_a_variant(roots, brief_id)
        return Page(url, "Snap-fit design guide", GUIDE_TEXT, "ab" * 32)

    with pytest.raises(CheckRefused, match="already holds variants in slots 1"):
        write_check(roots, brief_id, requirement_id, snap_fit(), fetcher=build_then_fetch)
    assert store.checks_of(roots.projects, project_of(roots, brief_id)) == ()


def test_attack_a_check_for_a_requirement_a_team_check_decides_is_refused(roots: Roots) -> None:
    brief = briefs.create_brief(roots, "A hook under 150 g", new_project_id())
    mass = TypeAdapter[Target](Target).validate_python(
        {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}
    )
    [requirement] = briefs.propose(roots, brief.id, [Draft(mass, "under 150 g")]).requirements
    with pytest.raises(CheckRefused, match="is not an unchecked requirement"):
        write_check(roots, brief.id, requirement.id, snap_fit(), fetcher=fetching())


def test_attack_a_check_for_another_briefs_requirement_is_refused(roots: Roots) -> None:
    _, theirs = unchecked_brief(roots)
    mine, _ = unchecked_brief(roots)
    with pytest.raises(CheckRefused, match="is not an unchecked requirement"):
        write_check(roots, mine, theirs, snap_fit(), fetcher=fetching())


def test_a_brief_holds_at_most_four_checks(roots: Roots) -> None:
    brief_id, requirement_id = unchecked_brief(roots)
    for _ in range(4):
        write_check(roots, brief_id, requirement_id, snap_fit(), fetcher=fetching())
    with pytest.raises(CheckRefused, match="already has 4 agent-written checks"):
        write_check(roots, brief_id, requirement_id, snap_fit(), fetcher=fetching())


def test_attack_a_record_the_store_did_not_sign_is_refused_on_read(roots: Roots) -> None:
    stored = write(roots)
    project = ProjectId(stored.check.project)
    [path] = (roots.projects / project / "agent_checks").glob("*.signed")
    path.write_bytes(path.read_bytes().replace(b"Snap arm strain", b"Snap arm strein"))
    with pytest.raises(CheckRefused, match="cannot be read"):
        store.checks_of(roots.projects, project)


def test_attack_a_bare_geometry_measure_is_refused(roots: Roots) -> None:
    reason = refused(
        roots,
        formula="h",
        inputs={"h": "geometry:h"},
        sources=[],
        example={**snap_fit().example.model_dump(), "inputs": {"h": {"value": 2, "unit": "mm"}}},
    )
    assert "a bare geometry or team measure is not an agent-written check" in reason


def test_attack_a_bare_team_measure_is_refused(roots: Roots) -> None:
    reason = refused(
        roots,
        formula="w",
        geometry=None,
        inputs={"w": "team:min_wall:min_wall"},
        sources=[],
        limit={"comparator": "at_least", "unit": "mm"},
        example={
            **snap_fit().example.model_dump(),
            "inputs": {"w": {"value": 2, "unit": "mm"}},
            "result": {"value": 2, "unit": "mm"},
        },
    )
    assert "a bare geometry or team measure" in reason


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"formula": "k * h * y / l**2 * z"}, "the formula reads z, which inputs does not bind"),
        ({"formula": "k * h * y"}, "inputs binds l, which the formula never reads"),
        (
            {"inputs": {"k": "source:k", "h": "geometry:h", "l": "geometry:l", "y": "web:y"}},
            "is not geometry:<name>",
        ),
        (
            {
                "inputs": {
                    "k": "source:k",
                    "h": "geometry:h",
                    "l": "geometry:l",
                    "y": "team:mass:mass",
                }
            },
            "binds no team measure",
        ),
        (
            {"inputs": {"k": "source:q", "h": "geometry:h", "l": "geometry:l", "y": "geometry:y"}},
            "which sources does not hold",
        ),
        (
            {
                "inputs": {
                    "k": "material:hardness",
                    "h": "geometry:h",
                    "l": "geometry:l",
                    "y": "geometry:y",
                }
            },
            "material:<field> with a field of",
        ),
        ({"geometry": None}, "geometry code is passed exactly when"),
        (
            {"limit": {"comparator": "at_most", "unit": "%", "source": "q"}},
            "the limit reads source q",
        ),
        ({"limit": {"comparator": "at_most", "unit": "furlong"}}, "the limit is in 'furlong'"),
        ({"formula": "k * h * y / l"}, "but the limit is in %"),
        ({"formula": "k * h + y / l**2"}, "joins values of different kinds"),
        ({"formula": "__import__('os').system('true')"}, "the formula may hold only"),
    ],
)
def test_attack_a_check_that_breaks_a_form_or_units_rule_is_refused(
    roots: Roots, changes: dict[str, Any], reason: str
) -> None:
    assert reason in refused(roots, **changes)


def test_two_sources_may_not_share_a_name(roots: Roots) -> None:
    [k] = snap_fit().sources
    assert "two sources share a name" in refused(roots, sources=[k, k])


def test_a_source_neither_the_formula_nor_the_limit_reads_is_refused(roots: Roots) -> None:
    [k] = snap_fit().sources
    unread = k.model_copy(update={"name": "q"})
    assert "sources holds q, which neither" in refused(roots, sources=[k, unread])


def test_attack_a_number_that_is_not_finite_is_refused_before_any_gate() -> None:
    with pytest.raises(ValidationError):
        snap_fit(
            example={**snap_fit().example.model_dump(), "result": {"value": "inf", "unit": "%"}}
        )


def test_attack_an_example_whose_quote_is_not_on_the_page_is_refused(roots: Roots) -> None:
    moved = EXAMPLE_QUOTE.replace("deflected", "bent")
    example = {**snap_fit().example.model_dump(), "quote": moved}
    assert "does not appear on" in refused(roots, example=example)


def test_attack_an_example_input_not_written_in_its_quote_is_refused(roots: Roots) -> None:
    example = snap_fit().example.model_dump()
    example["inputs"]["l"] = {"value": 25, "unit": "mm"}
    reason = refused(roots, example=example)
    assert "the example's l, 25, is not written in its quote" in reason


def test_attack_a_formula_that_misses_the_pages_own_result_is_refused(roots: Roots) -> None:
    [k] = snap_fit().sources
    page = GUIDE_TEXT.replace("1.5 times", "1.75 times")
    reason = refused(
        roots,
        sources=[k.model_copy(update={"value": 1.75, "quote": k.quote.replace("1.5", "1.75")})],
        fetcher=fetching({GUIDE: page}),
    )
    assert (
        "on the example's inputs the formula gives 0.875 %, but the example writes 0.75" in reason
    )


def test_attack_a_source_value_not_written_in_its_quote_is_refused(roots: Roots) -> None:
    [k] = snap_fit().sources
    reason = refused(roots, sources=[k.model_copy(update={"value": 1.6})])
    assert "source k: 1.6 is not written in its quote" in reason


def test_a_page_the_server_cannot_fetch_is_refused_with_the_reason(roots: Roots) -> None:
    reason = refused(roots, fetcher=fetching({}))
    assert f"source k: {GUIDE} answered 404" in reason


def test_a_pdf_example_cites_the_page_it_is_on(roots: Roots) -> None:
    pages = ("Contents", GUIDE_TEXT)
    stored = write(roots, fetcher=lambda url: PdfText(url, "Snap-fit guide", pages, "cd" * 32))
    assert stored.check.example.cited.page == 2


def test_the_example_may_round_its_result(roots: Roots) -> None:
    page = GUIDE_TEXT.replace("0.75 %", "0.8 %")
    example = {**snap_fit().example.model_dump(), "quote": EXAMPLE_QUOTE.replace("0.75", "0.8")}
    example["result"] = {"value": 0.8, "unit": "%"}
    stored = write(roots, example=example, fetcher=fetching({GUIDE: page}))
    assert stored.check.example.computed == pytest.approx(0.75)

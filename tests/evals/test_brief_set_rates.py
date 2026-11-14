"""A brief's rates rest on its best variant, so the order the agent scored its options in does
not move them."""

from pathlib import Path

import pytest
from outcome import Share
from tracefacts import trace_session

from cad.briefs.store import ConfirmedSet
from cad.checks.report import QUICK
from cad.checks.result import CheckResult, Measure
from cad.scorecard.model import Scorecard
from cad.scorecard.requirements import against
from cad.tables.materials import UNITS
from tests.support.cards import (
    confirm_on_page,
    drafts,
    genuine_card,
    genuine_result,
    transcript_of,
    write_transcript,
)
from tests.support.readings import a_session, built, store_quick

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")


def weighing(kilograms: float, result: CheckResult) -> CheckResult:
    if result.check_id != "mass":
        return result
    mass = Measure(name="mass", value=UNITS.Quantity(kilograms, "kg"))
    measured = tuple(mass if one.name == "mass" else one for one in result.measured)
    return result.model_copy(update={"measured": measured})


def scored(variants: Path, code: str, kilograms: float, confirmed: ConfirmedSet) -> Scorecard:
    held = built(variants, code)
    results = tuple(weighing(kilograms, genuine_result(spec)) for spec in QUICK)
    store_quick(variants, held, results)
    card = genuine_card(variant_id=held.id, results=results)
    return card.model_copy(update={"basis": against(confirmed)(card.finished)})


@pytest.mark.parametrize("light_last", [True, False])
def test_a_briefs_rates_rest_on_its_best_variant_in_either_order(
    tmp_path: Path, light_last: bool
) -> None:
    home, variants, roots, brief_id = a_session(tmp_path)
    confirmed = confirm_on_page(roots, brief_id, drafts(LIGHT))
    light = scored(variants, "x = 1\n", 0.1, confirmed)
    heavy = scored(variants, "x = 2\n", 1.0, confirmed)
    write_transcript(variants, *((heavy, light) if light_last else (light, heavy)))
    traced = trace_session(home, transcript_of(variants))
    assert traced.traced, traced.untraced
    assert traced.strict_pass == Share(numerator=1, denominator=1)

from types import SimpleNamespace
from typing import cast

import pytest

from cad.operations import auto, scorecards
from cad.operations.model import Tenant
from cad.scorecard.material import ReportedScorecard

TENANT = cast("Tenant", SimpleNamespace())
SCORED = scorecards.ScoreVariantInput(variant_id="v")


def card(*pending: str) -> ReportedScorecard:
    return cast("ReportedScorecard", SimpleNamespace(pending=pending))


def test_a_revision_is_scored_again_until_no_check_is_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cards = iter([card("fea"), card("fea"), card()])
    monkeypatch.setattr(scorecards, "score_variant", lambda tenant, scored: next(cards))  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
    assert auto.score_until_settled(TENANT, SCORED).pending == ()
    assert next(cards, None) is None


def test_the_wait_ends_at_its_limit_with_the_check_still_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[scorecards.ScoreVariantInput] = []

    def score(_: Tenant, scored: scorecards.ScoreVariantInput) -> ReportedScorecard:
        asked.append(scored)
        return card("fea")

    monkeypatch.setattr(scorecards, "score_variant", score)
    monkeypatch.setattr(auto, "SETTLE_SECONDS", 0)
    assert auto.score_until_settled(TENANT, SCORED).pending == ("fea",)
    assert asked == [SCORED]

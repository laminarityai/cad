from cad.scorecard.material import MaterialUse, ReportedScorecard, SetByAgent, snapshot
from tests.scorecard.test_score import offline_card


def reported(material_key: str = "prusament-pla") -> ReportedScorecard:
    card = offline_card().model_copy(update={"material_key": material_key})
    return ReportedScorecard(
        **dict(card), material=MaterialUse(key=material_key, set_by=SetByAgent())
    )


def test_one_card_has_one_etag_and_a_changed_card_has_another() -> None:
    first = snapshot(reported())
    assert snapshot(reported()).etag == first.etag
    assert snapshot(reported("generic-petg")).etag != first.etag


def test_a_snapshot_is_the_card_and_its_etag_and_nothing_else() -> None:
    card = reported()
    snap = snapshot(card)
    assert snap.model_dump(by_alias=True) == {**card.model_dump(by_alias=True), "etag": snap.etag}

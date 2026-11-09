from pathlib import Path

from cards import genuine_card, trace
from provenance import NotVerified, Resolved

from cad.scorecard.model import AgentMeasurement, AgentValue
from cad.tables.materials import UNITS

ROW = AgentMeasurement(
    requirement_id="r2",
    title="Smallest hole diameter",
    code_sha256="0" * 64,
    code="report('smallest_hole', 4.2, 'mm')",
    values=(AgentValue(name="smallest_hole", value=UNITS.Quantity(4.2, "mm")),),
    failed=None,
)


def test_an_agent_measurement_is_not_verified_and_fails_nothing(store: Path) -> None:
    card = genuine_card().model_copy(update={"not_verified": (ROW,)})
    traced = trace(card, store)
    agent = [one for one in traced.numbers if one.label.startswith("not_verified")]
    assert [(one.label, one.value, one.outcome) for one in agent] == [
        ("not_verified[0].values[0].value", "4.2 mm", NotVerified())
    ]
    assert traced.failures == ()
    rest = [one.outcome for one in traced.numbers if one not in agent]
    assert rest and all(isinstance(outcome, Resolved) for outcome in rest)


def test_a_card_with_no_agent_measurement_dumps_as_before() -> None:
    assert "not_verified" not in genuine_card().model_dump_json()

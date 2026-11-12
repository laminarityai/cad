"""Repeat and turn without a container: the sandbox answers are given, and the gate judges them.
test_turned_sandbox.py runs the same attacks in real containers."""

from collections.abc import Callable, Sequence

import pytest

from cad.agent_checks import gates, harness, probes
from cad.agent_checks.harness import Failed, Motion, Outcome, Reading, Shape, Slot, Values
from tests.support.agent_checks import snap_fit

type Answer = Callable[[int, bool], Outcome]


def values(h: float, length: float, y: float, unit: str = "mm") -> Values:
    return Values((Reading("h", h, unit), Reading("l", length, "mm"), Reading("y", y, "mm")), 0)


def judged(monkeypatch: pytest.MonkeyPatch, answer: Answer) -> str | None:
    """The gate's answer when probe number n, turned or not, gives answer(n, turned)."""

    def run(
        shapes: Sequence[Shape], slots: Sequence[Slot], motion: Motion | None = None
    ) -> tuple[Outcome, ...]:
        return tuple(answer(one.shape, motion is not None) for one in slots)

    monkeypatch.setattr(harness, "run", run)
    draft = snap_fit()
    shaped = gates.form(draft)
    assert isinstance(shaped, gates.Shaped)
    return probes.repeat_and_turn(draft, shaped)


def test_values_that_change_with_the_probe_and_not_the_turn_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert judged(monkeypatch, lambda n, turned: values(2 + n, 20 + n, 1 + n)) is None


def turn_changes_it(n: int, turned: bool) -> Outcome:
    return values(3 if turned else 2, 20, 1)


def same_y_everywhere(n: int, turned: bool) -> Outcome:
    return values(2 + n, 20 + n, 1)


def an_angle(n: int, turned: bool) -> Outcome:
    return values(2 + n, 20 + n, 1 + n, "deg")


def fails_turned(n: int, turned: bool) -> Outcome:
    return Failed("ValueError()") if turned else values(2 + n, 20 + n, 1 + n)


def times_out(n: int, turned: bool) -> Outcome:
    return Failed("timed out after 30 s")


def only_h(n: int, turned: bool) -> Outcome:
    return Values((Reading("h", 2 + n, "mm"),), 0)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (turn_changes_it, "different answers when the part was turned"),
        (same_y_everywhere, "gave y = 1 mm on each of"),
        (an_angle, "h is in deg"),
        (fails_turned, "failed on the part turned and moved"),
        (times_out, "no values on any probe shape"),
        (only_h, "it reported h, but the formula reads h, l, y"),
    ],
)
def test_untrustworthy_geometry_code_is_refused(
    monkeypatch: pytest.MonkeyPatch, answer: Answer, reason: str
) -> None:
    refused = judged(monkeypatch, answer)
    assert refused is not None
    assert reason in refused


def test_one_probe_the_code_cannot_measure_does_not_refuse_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answer(n: int, turned: bool) -> Outcome:
        return Failed("no arm here") if n == 0 else values(2 + n, 20 + n, 1 + n)

    assert judged(monkeypatch, answer) is None


def test_a_check_with_no_geometry_code_needs_no_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(*args: object) -> tuple[Outcome, ...]:
        raise AssertionError("no container should run")

    monkeypatch.setattr(harness, "run", unreachable)
    shaped = gates.form(snap_fit())
    assert isinstance(shaped, gates.Shaped)
    assert probes.repeat_and_turn(snap_fit(geometry=None), shaped) is None

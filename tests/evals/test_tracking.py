from tracking import (
    Ratio,
    RequirementOutcome,
    describe,
    track,
)

from cad.checks.result import Verdict


def outcome(verdict: Verdict, reviewed: bool) -> RequirementOutcome:
    return RequirementOutcome("r", verdict, reviewed)


def test_only_a_pass_by_a_reviewed_check_counts_as_a_strict_pass() -> None:
    tracking = track(
        (
            outcome(Verdict.PASS, reviewed=True),
            outcome(Verdict.PASS, reviewed=False),
            outcome(Verdict.FAIL, reviewed=True),
            outcome(Verdict.UNKNOWN, reviewed=False),
        )
    )
    assert tracking.strict_pass_rate == Ratio(1, 4)
    assert tracking.reviewed_coverage == Ratio(2, 4)
    assert describe(tracking.strict_pass_rate) == "1/4 (25%)"

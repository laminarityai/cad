import sys

import agree
import pytest
import session


def test_both_harnesses_read_a_failed_drive_by_the_drivers_one_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session.failure_note("", "")
    driver = sys.modules["claude_session"]
    lines: tuple[str, ...] = driver.FAILURE_LINES
    monkeypatch.setattr(driver, "FAILURE_LINES", (*lines, "a new failure:"))
    stdout = "init: cad connected\nresult: a reply\na new failure: why\n"
    assert agree.session_failure(stdout, "") == "a new failure: why"
    assert session.failure_note(stdout, "") == "a new failure: why"

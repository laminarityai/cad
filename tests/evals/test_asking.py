from typing import Any

from asking import STATED, Asking, Call, asking_of
from inprocess import asked_only, calls_of

QUESTIONS: dict[str, Any] = {"questions": [{"question": "How big?"}, {"question": "What for?"}]}
NOTHING: dict[str, Any] = {}


def test_a_session_that_read_and_asked_before_building_says_so() -> None:
    calls: list[Call] = [
        ("mcp__cad__search_knowledge", NOTHING),
        ("mcp__cad__ask_questions", QUESTIONS),
        ("mcp__cad__create_brief", NOTHING),
        ("mcp__cad__build_variant", NOTHING),
    ]
    assert asking_of(calls, {}) == Asking(
        asked_before_build=True, questions=2, searched_before_build=True
    )


def test_a_search_or_a_question_after_the_first_build_does_not_count() -> None:
    calls: list[Call] = [
        ("build_variant", NOTHING),
        ("web_search", NOTHING),
        ("ask_questions", QUESTIONS),
    ]
    assert asking_of(calls, {}) == Asking(
        asked_before_build=False, questions=0, searched_before_build=False
    )


def test_a_fully_stated_brief_is_marked_by_whether_it_got_questions() -> None:
    assert asking_of([("build_variant", NOTHING)], {STATED: True}).stated_unasked is True
    asked: list[Call] = [("build_variant", NOTHING), ("ask_questions", QUESTIONS)]
    assert asking_of(asked, {STATED: True}).stated_unasked is False


def test_the_in_process_run_reads_web_searches_and_waits_only_on_unanswered_questions() -> None:
    asked: list[dict[str, Any]] = [
        {"kind": "web_search", "call_id": "s", "query": "impeller"},
        {"kind": "tool_call", "call_id": "a", "name": "ask_questions", "input": QUESTIONS},
    ]
    assert calls_of(asked) == [("web_search", {}), ("ask_questions", QUESTIONS)]
    assert asked_only(asked)
    stored = [
        *asked,
        {"kind": "tool_call", "call_id": "b", "name": "create_brief", "input": NOTHING},
    ]
    assert not asked_only(stored)

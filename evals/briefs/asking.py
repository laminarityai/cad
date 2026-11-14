from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from cad.frozen import Frozen

STATED: Final = "stated"
ASK: Final = "ask_questions"
BUILDS: Final = frozenset({"build_variant", "auto_revise"})
SEARCHES: Final = frozenset({"search_knowledge", "web_search", "WebSearch"})
PREFIX: Final = "mcp__cad__"

type Call = tuple[str, Mapping[str, Any]]


class Asking(Frozen):
    asked_before_build: bool
    questions: int
    searched_before_build: bool
    stated_unasked: bool | None = None


def asking_of(calls: Sequence[Call], grader: Mapping[str, Any]) -> Asking:
    names = [(name.removeprefix(PREFIX), given) for name, given in calls]
    first = next((at for at, (name, _) in enumerate(names) if name in BUILDS), len(names))
    before = names[:first]
    asked = [given for name, given in before if name == ASK]
    questions: object = asked[0].get("questions") if asked else None
    return Asking(
        asked_before_build=bool(asked),
        questions=len(cast(list[object], questions)) if isinstance(questions, list) else 0,
        searched_before_build=any(name in SEARCHES for name, _ in before),
        stated_unasked=all(name != ASK for name, _ in names)
        if grader.get(STATED) is True
        else None,
    )

import ast
from collections.abc import Callable
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
ANSWER_RECORDS = {"PageAnswer", "ItemAnswer", "Decision"}


def named(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.alias):
        return node.name.rpartition(".")[2]
    return None


def files_where(matches: Callable[[ast.AST], bool]) -> set[str]:
    return {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if any(matches(node) for node in ast.walk(ast.parse(path.read_text())))
    }


def test_only_the_page_builds_or_appends_an_answer() -> None:
    building = files_where(lambda n: isinstance(n, ast.Call) and named(n.func) in ANSWER_RECORDS)
    appending = files_where(lambda n: named(n) == "append_answer")
    assert building | appending == {"cad/confirmations/page.py"}


def test_only_the_transport_calls_the_page_answer() -> None:
    assert files_where(lambda n: named(n) == "answer_page") == {"cad/confirmations/http.py"}

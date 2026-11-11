import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).parent
ADVICE = (
    "Move the shared helper into a module under tests/support/ and import it from "
    "tests.support.<module>. Fixtures go in the nearest conftest.py and are never imported."
)


def is_test_module(name: str) -> bool:
    last = name.rsplit(".", 1)[-1]
    return last == "conftest" or last.startswith("test_")


def imported_from_tests(tree: ast.AST) -> list[tuple[int, str]]:
    """Every import in `tree` that names a test file, a conftest, or a tests package other than
    tests.support, as (line, dotted name)."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            named = [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = "." * node.level + (node.module or "")
            named = [(node.lineno, base)] + [
                (node.lineno, f"{base}.{alias.name}".lstrip(".")) for alias in node.names
            ]
        else:
            continue
        for line, name in named:
            under_tests = name == "tests" or name.startswith("tests.")
            outside_support = under_tests and not name.startswith("tests.support")
            if is_test_module(name) or (outside_support and name != "tests"):
                found.append((line, name))
                break
    return found


def violations(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root.parent)}:{line} imports {name}"
        for path in sorted(root.rglob("*.py"))
        if "__pycache__" not in path.parts
        for line, name in imported_from_tests(ast.parse(path.read_text()))
    ]


@pytest.mark.parametrize(
    "source",
    [
        "from tests.checks.test_lanes import job",
        "from test_anchors import case",
        "from .test_run import running",
        "from . import test_run",
        "import conftest",
        "from conftest import Person",
        "from tests.conftest import Person",
        "from tests.chat.support import Chat",
        "from auto.conftest import Session",
    ],
)
def test_the_check_names_an_import_of_another_test_file(source: str) -> None:
    assert imported_from_tests(ast.parse(source)) != []


@pytest.mark.parametrize(
    "source",
    [
        "from tests.support.chat import Chat",
        "from tests.support import chat",
        "from cad.conftest_like import x",
        "import pytest",
    ],
)
def test_the_check_lets_tests_import_from_tests_support(source: str) -> None:
    assert imported_from_tests(ast.parse(source)) == []


def test_no_test_file_imports_another_test_file() -> None:
    found = violations(TESTS)
    assert found == [], f"{ADVICE}\n" + "\n".join(found)

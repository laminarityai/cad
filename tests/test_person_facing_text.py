import ast
import re
from pathlib import Path

import cad

SOURCE = Path(cad.__file__).parent
OPERATOR = re.compile(r"\boperator\b", re.IGNORECASE)


def docstrings(tree: ast.Module) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, owners)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def test_no_text_the_server_sends_asks_for_the_operator() -> None:
    """The product is hosted, so a person or the agent can never touch the server's files. A
    message that says the operator must act names an action nobody who reads it can take."""
    found: list[str] = []
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        skip = docstrings(tree)
        found.extend(
            f"{path.relative_to(SOURCE)}:{node.lineno}: {node.value!r}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in skip
            and OPERATOR.search(node.value)
        )
    assert found == []

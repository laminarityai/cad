import ast
from pathlib import Path

import cad

SRC = Path(cad.__file__).parent


def cad_imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return {name for name in found if name.startswith("cad.")}


def test_records_and_the_data_root_import_no_feature() -> None:
    """Every feature stores through records/, so records/ importing a feature is a cycle in
    waiting. SandboxUnavailable is the one exception: the key raises it, and the job lanes and
    the confirmation page catch it by that type."""
    allowed = ("cad.errors.", "cad.data_root.", "cad.records.", "cad.sandbox.outcome.Sandbox")
    imported = {name for path in (SRC / "records").glob("*.py") for name in cad_imports(path)}
    assert sorted(name for name in imported if not name.startswith(allowed)) == []
    assert cad_imports(SRC / "data_root.py") == set()

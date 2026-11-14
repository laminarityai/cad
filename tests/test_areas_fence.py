"""Colour is how a model looks, never a result. Only the modules that carry the areas from the
runner to the viewer and the STEP may touch them: a check, a table read, a verdict or Auto that
reads one would let the agent's paint decide something. So would `outcome == Built()`, which a
coloured build fails: it once kept every coloured build out of its set."""

import ast
from pathlib import Path

from cad.checks import jobs
from cad.checks.container.wire import LoadCaseWire
from cad.checks.report import build_request
from cad.sandbox.outcome import Area
from cad.tables.materials import load_materials
from cad.variants.entry import Entry, VariantId

SOURCE = Path(__file__).parents[1] / "src" / "cad"
CARRIERS = frozenset(
    {
        "sandbox/outcome.py",
        "sandbox/host.py",
        "sandbox/runner.py",
        "sandbox/wire.py",
        "variants/entry.py",
        "variants/store.py",
        "operations/reads.py",
        "operations/exports.py",
        "geometry/exports/job.py",
        "geometry/exports/lane.py",
        "geometry/container/export.py",
        "geometry/container/coloured_step.py",
    }
)
COLOUR_NAMES = frozenset({"Area", "Areas", "AREAS", "read_areas", "on_faces", "MAX_AREAS"})
COLOUR_FIELDS = frozenset({"areas", "areas_dropped"})
CASE: LoadCaseWire = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
}


def touches_colour(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in COLOUR_FIELDS:
            found.append(f"line {node.lineno}: .{node.attr}")
        if isinstance(node, ast.Compare) and any(
            map(is_built_call, [node.left, *node.comparators])
        ):
            found.append(f"line {node.lineno}: == Built()")
        if isinstance(node, ast.ImportFrom) and node.module == "cad.sandbox.outcome":
            found += [f"line {node.lineno}: {a.name}" for a in node.names if a.name in COLOUR_NAMES]
    return found


def is_built_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Built"
    )


def test_only_the_carriers_touch_the_areas() -> None:
    touched = {
        str(path.relative_to(SOURCE)): hits
        for path in sorted(SOURCE.rglob("*.py"))
        if (hits := touches_colour(ast.parse(path.read_text())))
    }
    assert set(touched) <= CARRIERS, {k: v for k, v in touched.items() if k not in CARRIERS}


def test_the_fence_sees_a_check_that_reads_the_areas() -> None:
    sneaky = "from cad.sandbox.outcome import Areas\n\ndef run(held):\n    return held.areas\n"
    assert touches_colour(ast.parse(sneaky)) == ["line 1: Areas", "line 4: .areas"]
    assert touches_colour(ast.parse("ok = built.outcome == Built()\n")) == ["line 1: == Built()"]


def test_the_checks_a_variant_gets_do_not_depend_on_its_colours(tmp_path: Path) -> None:
    table = load_materials()
    request = build_request("prusament-petg", table)
    demand = jobs.Demand(loads={"c1": CASE})
    grey = Entry(VariantId("0123456789abcdef"), tmp_path, b"brep", "b" * 64)
    painted = Entry(
        grey.id, tmp_path, b"brep", "b" * 64, (Area(name="grip", colour="#1a1a1a", faces=(0,)),)
    )
    assert jobs.plan(tmp_path, painted, request, table, demand) == jobs.plan(
        tmp_path, grey, request, table, demand
    )

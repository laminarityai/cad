"""Colour is how a model looks, never a result. Only the modules that carry the areas from the
runner to the viewer and the STEP may touch them: a check, a table read, a verdict or Auto that
reads one would let the agent's paint decide something. So would `outcome == Built()`, which a
coloured build fails: it once kept every coloured build out of its set.

The scan is a tripwire, not a proof: it reads names, so a determined path around it exists. The
behavioural guard is the `jobs.plan` equality test below. A check's job key hashes the
variant's `brep_sha256`, and colour is not in the BREP, so a coloured variant and a grey one
get the same checks."""

import ast
from pathlib import Path
from typing import cast

import pytest

from cad.checks import jobs
from cad.checks.container.wire import LoadCaseWire, RequestWire, ValueWire
from cad.checks.report import build_request
from cad.checks.result import BodyMaterial
from cad.sandbox.bodies import BODIES
from cad.sandbox.outcome import Area
from cad.tables.materials import load_materials
from cad.variants.entry import Entry, VariantId
from tests.support.named_bodies import GEAR, PLATE, PLATE_AND_GEARS

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
COLOUR_NAMES = frozenset(
    {"Area", "Areas", "AREAS", "read_areas", "on_faces", "MAX_AREAS", "ToldOutcome", "told"}
)
TELLS_THE_AGENT = {"operations/variants.py": frozenset({"ToldOutcome", "told"})}
COLOUR_FIELDS = frozenset({"areas", "areas_dropped"})
LOOKUPS = frozenset({"getattr", "hasattr", "setattr", "delattr"})
HOLDERS = frozenset({"outcome", "manifest", "built"})
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
        if isinstance(node, ast.Attribute) and node.attr in COLOUR_NAMES:
            found.append(f"line {node.lineno}: .{node.attr}")
        if isinstance(node, ast.Call) and is_named_lookup(node):
            found.append(f"line {node.lineno}: getattr {cast(ast.Constant, node.args[1]).value}")
        if isinstance(node, ast.Call) and dumps_an_outcome(node):
            found.append(f"line {node.lineno}: dump of outcome")
        if isinstance(node, ast.Subscript) and is_colour_key(node.slice):
            found.append(f"line {node.lineno}: [{cast(ast.Constant, node.slice).value!r}]")
        if isinstance(node, ast.Attribute | ast.Call) and holder_name(node) in HOLDERS:
            found.append(f"line {node.lineno}: namespace of {holder_name(node)}")
        if isinstance(node, ast.MatchClass) and COLOUR_FIELDS & set(node.kwd_attrs):
            found += [
                f"line {node.lineno}: case {k}=" for k in node.kwd_attrs if k in COLOUR_FIELDS
            ]
    return found


def is_named_lookup(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Name)
        and node.func.id in LOOKUPS
        and len(node.args) > 1
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in COLOUR_FIELDS
    )


def dumps_an_outcome(node: ast.Call) -> bool:
    """A whole build outcome dumped, such as to a hash, carries its areas with it."""
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr.startswith("model_dump")):
        return False
    held = func.value
    if isinstance(held, ast.Call) and isinstance(held.func, ast.Name):
        return held.func.id == "told"
    return name_of(held) in HOLDERS


def is_colour_key(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value in COLOUR_FIELDS


def holder_name(node: ast.Attribute | ast.Call) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr == "__dict__":
        return name_of(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "vars":
        return name_of(node.args[0]) if node.args else None
    return None


def name_of(node: ast.expr) -> str | None:
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", None)


def is_built_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Built"
    )


def test_only_the_carriers_touch_the_areas() -> None:
    touched = {
        str(path.relative_to(SOURCE)): hits
        for path in sorted(SOURCE.rglob("*.py"))
        if (
            hits := [
                hit
                for hit in touches_colour(ast.parse(path.read_text()))
                if hit.split(": ")[-1] not in TELLS_THE_AGENT.get(str(path.relative_to(SOURCE)), ())
            ]
        )
    }
    assert set(touched) <= CARRIERS, {k: v for k, v in touched.items() if k not in CARRIERS}


def test_the_fence_sees_a_check_that_reads_the_areas() -> None:
    sneaky = "from cad.sandbox.outcome import Areas\n\ndef run(held):\n    return held.areas\n"
    assert touches_colour(ast.parse(sneaky)) == ["line 1: Areas", "line 4: .areas"]
    assert touches_colour(ast.parse("ok = built.outcome == Built()\n")) == ["line 1: == Built()"]


@pytest.mark.parametrize(
    ("sneaky", "found"),
    [
        pytest.param('getattr(held, "areas")', "line 1: getattr areas", id="getattr"),
        pytest.param(
            "sha256(manifest.outcome.model_dump_json().encode())",
            "line 1: dump of outcome",
            id="dump",
        ),
        pytest.param("outcome.read_areas(raw)", "line 1: .read_areas", id="through-the-module"),
        pytest.param(
            "match built:\n    case Built(areas=painted):\n        pass",
            "line 2: case areas=",
            id="match",
        ),
        pytest.param("sha256(built.model_dump_json())", "line 1: dump of outcome", id="built"),
        pytest.param("told(o).model_dump()", "line 1: dump of outcome", id="told"),
        pytest.param("painted = held['areas']", "line 1: ['areas']", id="key"),
        pytest.param("everything = outcome.__dict__", "line 1: namespace of outcome", id="dict"),
        pytest.param("everything = vars(outcome)", "line 1: namespace of outcome", id="vars"),
        pytest.param(
            "from cad.sandbox.outcome import ToldOutcome", "line 1: ToldOutcome", id="told-import"
        ),
    ],
)
def test_the_fence_sees_the_areas_read_another_way(sneaky: str, found: str) -> None:
    assert touches_colour(ast.parse(sneaky)) == [found]


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


def test_a_body_name_selects_solids_and_carries_no_number() -> None:
    table = load_materials()
    renamed = BODIES.validate_python(
        [{"name": "base", "solids": (0,)}, {"name": "teeth", "solids": (1, 2)}]
    )
    named = build_request(
        (BodyMaterial(body="plate", key=PLATE), BodyMaterial(body="gear", key=GEAR)),
        table,
        bodies=PLATE_AND_GEARS,
    )
    other = build_request(
        (BodyMaterial(body="base", key=PLATE), BodyMaterial(body="teeth", key=GEAR)),
        table,
        bodies=renamed,
    )

    def each_solid(wire: RequestWire) -> dict[int, dict[str, ValueWire]]:
        return {i: one["values"] for one in wire["bodies"] for i in one["solids"]}

    assert each_solid(named.wire) == each_solid(other.wire)


def test_the_checks_of_named_bodies_do_not_depend_on_their_colours(tmp_path: Path) -> None:
    table = load_materials()
    made = (BodyMaterial(body="plate", key=PLATE), BodyMaterial(body="gear", key=GEAR))
    request = build_request(made, table, bodies=PLATE_AND_GEARS)
    demand = jobs.Demand(loads={"c1": CASE})
    grey = Entry(VariantId("0123456789abcdef"), tmp_path, b"brep", "b" * 64, (), PLATE_AND_GEARS)
    painted = Entry(
        grey.id,
        tmp_path,
        b"brep",
        "b" * 64,
        (
            Area(name="plate", colour="#1a1a1a", faces=(0,)),
            Area(name="gear", colour="#808080", faces=(6,)),
        ),
        PLATE_AND_GEARS,
    )
    assert jobs.plan(tmp_path, painted, request, table, demand) == jobs.plan(
        tmp_path, grey, request, table, demand
    )

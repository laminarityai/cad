import json
from pathlib import Path
from typing import Any

import pytest

from cad.checks.container.check import Quick
from cad.checks.container.wire import LoadCaseWire
from cad.checks.jobs import FEA, JobSpec
from cad.checks.report import QUICK, SPECS, Request, build_request, parse, reads_of
from cad.checks.result import BodyMaterial, ReadCited, ReadMissing, Verdict
from cad.sandbox.bodies import BODIES, MAX_BODIES, MAX_SOLIDS
from cad.tables.materials import load_materials
from tests.support.check_reports import OWN_LIMITS, good_report, measured, sent
from tests.support.named_bodies import GEAR, PLATE, PLATE_AND_GEARS

TABLE = load_materials()
MADE_OF = (BodyMaterial(body="plate", key=PLATE), BodyMaterial(body="gear", key=GEAR))
ARGUMENT_CAP = 128 * 1024


def density(key: str) -> float:
    found = build_request(key, TABLE).wire["values"]["density"]
    assert found["kind"] == "known"
    return found["magnitude"]


def test_each_body_reaches_the_container_with_its_own_material_s_values() -> None:
    wire = build_request(MADE_OF, TABLE, bodies=PLATE_AND_GEARS).wire
    assert wire["values"] == {}
    sent = {one["name"]: (one["solids"], one["values"]["density"]) for one in wire["bodies"]}
    assert sent == {
        "plate": ([0], {"kind": "known", "magnitude": density(PLATE)}),
        "gear": ([1, 2], {"kind": "known", "magnitude": density(GEAR)}),
    }


@pytest.mark.parametrize(
    "material",
    [
        PLATE,
        (BodyMaterial(body="gear", key=GEAR), BodyMaterial(body="plate", key=PLATE)),
        (BodyMaterial(body="plate", key=PLATE),),
    ],
    ids=["one-key", "out-of-order", "a-body-left-out"],
)
def test_materials_that_do_not_name_each_body_in_order_build_no_request(
    material: str | tuple[BodyMaterial, ...],
) -> None:
    with pytest.raises(ValueError, match="bod"):
        build_request(material, TABLE, bodies=PLATE_AND_GEARS)


def test_the_body_list_and_its_materials_are_in_every_job_key() -> None:
    one = build_request(MADE_OF, TABLE, bodies=PLATE_AND_GEARS)
    swapped = (BodyMaterial(body="plate", key=GEAR), BodyMaterial(body="gear", key=PLATE))
    other = build_request(swapped, TABLE, bodies=PLATE_AND_GEARS)
    renamed = BODIES.validate_python(
        [{"name": "plate", "solids": (0, 1)}, {"name": "gear", "solids": (2,)}]
    )
    moved = build_request(MADE_OF, TABLE, bodies=renamed)
    assert len({key_of(made) for made in (one, other, moved)}) == 3


def key_of(request: Request) -> str:
    return JobSpec(Path("/nowhere"), "v" * 16, "a" * 64, QUICK, Quick(), request).key


def test_a_mass_read_cites_the_row_of_its_own_body() -> None:
    request = build_request(MADE_OF, TABLE, bodies=PLATE_AND_GEARS)
    mass = next(spec for spec in SPECS if spec.id == "mass")
    reads = reads_of(mass, request)
    assert [(type(one), one.body) for one in reads] == [(ReadCited, "plate"), (ReadCited, "gear")]


def test_a_body_whose_material_the_table_lacks_reads_missing_for_that_body_only() -> None:
    made = (BodyMaterial(body="plate", key=PLATE), BodyMaterial(body="gear", key="unobtainium"))
    request = build_request(made, TABLE, bodies=PLATE_AND_GEARS)
    mass = next(spec for spec in SPECS if spec.id == "mass")
    missing = [one.body for one in reads_of(mass, request) if isinstance(one, ReadMissing)]
    assert missing == ["gear"]


def report_of_bodies(gear_density: float) -> dict[str, Any]:
    report = good_report()
    report["results"][2]["measured"] = [
        measured("volume", 2000.0, "mm^3"),
        measured("volume:plate", 1000.0, "mm^3"),
        measured("density:plate", density(PLATE), "kg/mm^3"),
        measured("mass:plate", 1000.0 * density(PLATE), "kg"),
        measured("volume:gear", 1000.0, "mm^3"),
        measured("density:gear", gear_density, "kg/mm^3"),
        measured("mass:gear", 1000.0 * gear_density, "kg"),
        measured("mass", 1000.0 * (density(PLATE) + gear_density), "kg"),
    ]
    return report


def test_a_body_s_density_is_checked_against_what_the_host_sent_for_that_body() -> None:
    request = build_request(MADE_OF, TABLE, bodies=PLATE_AND_GEARS)
    honest = parse(sent(report_of_bodies(density(GEAR))), request, OWN_LIMITS)
    assert honest.results[2].verdict == Verdict.PASS
    swapped = parse(sent(report_of_bodies(density(PLATE))), request, OWN_LIMITS)
    assert {one.verdict for one in swapped.results} == {Verdict.UNKNOWN}
    assert "density:gear" in swapped.results[0].reason


def test_the_largest_request_a_variant_can_send_fits_one_container_argument() -> None:
    names = [f"{chr(ord('a') + n)}{'-' * 31}" for n in range(MAX_BODIES)]
    solids = [[n] for n in range(MAX_BODIES)]
    for extra in range(MAX_BODIES, MAX_SOLIDS):
        solids[extra % MAX_BODIES].append(extra)
    bodies = BODIES.validate_python(
        [{"name": name, "solids": tuple(held)} for name, held in zip(names, solids, strict=True)]
    )
    lacked = [f"{'x' * 60}{n:04d}" for n in range(MAX_BODIES)]
    for keys in (sorted(TABLE.materials, key=len)[-MAX_BODIES:], lacked):
        made = tuple(BodyMaterial(body=name, key=k) for name, k in zip(names, keys, strict=True))
        wire = build_request(made, TABLE, tuple(SPECS), bodies=bodies).wire
        size = len(json.dumps(wire).encode())
        assert size < ARGUMENT_CAP // 2, size


@pytest.mark.parametrize(("body", "cited"), [("plate", ["plate"]), (None, [])])
def test_a_stress_result_cites_only_the_body_its_load_case_solved(
    body: str | None, cited: list[str]
) -> None:
    case: LoadCaseWire = {
        "support": {"kind": "flat_end"},
        "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
    }
    if body is not None:
        case["body"] = body
    request = build_request(MADE_OF, TABLE, (FEA,), (case,), bodies=PLATE_AND_GEARS)
    report = good_report()
    report["results"] = [
        *report["results"][:2],
        {"id": "fea", "verdict": "unknown", "measured": [], "reason": "not solved"},
    ]
    stress = parse(sent(report), request, OWN_LIMITS).results[-1]
    assert stress.check_id == "fea"
    assert sorted({one.body for one in stress.reads}) == cited
    rows = {request.reads[key].source for key in request.reads if key[1] in cited}
    assert set(stress.sources) == {*FEA.sources, *rows}

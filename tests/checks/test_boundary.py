import json
from base64 import b64encode
from typing import Any

import pytest

from cad.checks.report import SPECS, Request, build_request, parse
from cad.checks.result import CheckRun, StepMissing, StepStored, Verdict
from cad.sandbox.container import Attended, ContainerState, Job, Ran, TooMuchOutput
from cad.tables.materials import Cited, Material, MaterialsTable, Unknown, load_materials

STEP = b"ISO-10303-21; fake STEP"
OWN_LIMITS = Job("check", "sha256:analysis", (), b"", wall_seconds=60, memory_mb=1536)
DIMENSIONLESS = "dimensionless"


def measured(name: str, magnitude: float, unit: str) -> dict[str, Any]:
    return {"name": name, "magnitude": magnitude, "unit": unit}


def good_report() -> dict[str, Any]:
    return {
        "kind": "checked",
        "results": [
            {
                "id": "closed_solid",
                "verdict": "pass",
                "measured": [
                    measured("solids", 1, DIMENSIONLESS),
                    measured("free_edges", 0, DIMENSIONLESS),
                    measured("over_used_edges", 0, DIMENSIONLESS),
                    measured("valid", 1, DIMENSIONLESS),
                ],
                "reason": "one valid solid",
            },
            {
                "id": "interference",
                "verdict": "pass",
                "measured": [
                    measured("bodies", 1, DIMENSIONLESS),
                    measured("interfering_pairs", 0, DIMENSIONLESS),
                    measured("max_common_volume", 0, "mm^3"),
                ],
                "reason": "one solid",
            },
            {
                "id": "mass",
                "verdict": "pass",
                "measured": [
                    measured("volume", 1000.0, "mm^3"),
                    measured("center_of_mass:x", 1.0, "mm"),
                    measured("density", 1.24e-6, "kg/mm^3"),
                    measured("mass", 1.24e-3, "kg"),
                ],
                "reason": "1000 mm^3",
            },
            {
                "id": "extents",
                "verdict": "pass",
                "measured": [
                    measured("extent:x", 10.0, "mm"),
                    measured("sorted_extent:smallest", 10.0, "mm"),
                ],
                "reason": "10 mm",
            },
        ],
        "step": {"kind": "written", "base64": b64encode(STEP).decode()},
    }


def ran(
    report: bytes | TooMuchOutput,
    *,
    killed: bool = False,
    oom: bool = False,
    exit_code: int = 0,
) -> Ran:
    state = ContainerState(Status="exited", ExitCode=exit_code, OOMKilled=oom, Error="")
    return Ran(Attended(killed_at_deadline=killed, report=report, output=""), state)


def sent(report: dict[str, Any]) -> Ran:
    return ran(json.dumps(report).encode())


def with_result(index: int, **changes: Any) -> dict[str, Any]:
    report = good_report()
    report["results"][index].update(changes)
    return report


@pytest.fixture(scope="module")
def request_for_pla() -> Request:
    return build_request("prusament-pla", load_materials())


def test_a_good_report_becomes_four_results_with_pint_quantities(request_for_pla: Request) -> None:
    parsed = parse(sent(good_report()), request_for_pla, OWN_LIMITS)
    assert [(result.check_id, result.verdict) for result in parsed.results] == [
        ("closed_solid", Verdict.PASS),
        ("interference", Verdict.PASS),
        ("mass", Verdict.PASS),
        ("extents", Verdict.PASS),
    ]
    assert parsed.step == STEP
    mass = parsed.results[2]
    assert mass.number("volume", "mm^3") == 1000.0
    assert mass.number("mass", "g") == pytest.approx(1.24)


def test_formula_sources_and_version_come_from_the_staged_checks_not_the_wire(
    request_for_pla: Request,
) -> None:
    report = good_report()
    for result in report["results"]:
        result.update(version="forged", formula="forged", sources=[{"url": "forged"}])
    parsed = parse(sent(report), request_for_pla, OWN_LIMITS)
    for result, spec in zip(parsed.results, SPECS, strict=True):
        assert (result.formula, result.sources[: len(spec.sources)], result.version) == (
            spec.formula,
            spec.sources,
            spec.version,
        )
        assert result.formula and result.sources


def test_mass_cites_the_datasheet_of_the_density_it_used(request_for_pla: Request) -> None:
    mass = parse(sent(good_report()), request_for_pla, OWN_LIMITS).results[2]
    density = load_materials().get_material("prusament-pla").density
    assert isinstance(density, Cited)
    assert mass.sources[-1] == density.source
    assert len(mass.sources) == len(SPECS[2].sources) + 1


def test_only_a_check_that_declares_a_read_cites_the_row_it_read(request_for_pla: Request) -> None:
    parsed = parse(sent(good_report()), request_for_pla, OWN_LIMITS)
    for result, spec in zip(parsed.results, SPECS, strict=True):
        assert len(result.sources) == len(spec.sources) + (1 if spec.reads else 0)


def test_every_declared_read_names_a_declared_measure() -> None:
    for spec in SPECS:
        assert set(spec.reads) <= set(spec.measures)


def test_a_read_that_differs_from_what_the_host_sent_is_refused(request_for_pla: Request) -> None:
    edited = [measured("density", 2.0e-6, "kg/mm^3")]
    seen = sent(with_result(2, measured=edited))
    parsed = parse(seen, request_for_pla, OWN_LIMITS)
    assert {result.verdict for result in parsed.results} == {Verdict.UNKNOWN}
    assert "mass: density" in parsed.results[0].reason


def test_a_read_when_the_host_sent_none_is_refused() -> None:
    request = build_request("unobtainium", load_materials())
    parsed = parse(sent(good_report()), request, OWN_LIMITS)
    assert {result.verdict for result in parsed.results} == {Verdict.UNKNOWN}
    assert "mass: density" in parsed.results[0].reason


def test_a_check_run_serializes_and_reads_back_equal(request_for_pla: Request) -> None:
    parsed = parse(sent(good_report()), request_for_pla, OWN_LIMITS)
    run = CheckRun(
        variant_id="0123456789abcdef",
        material_key="prusament-pla",
        table_version=request_for_pla.table_version,
        check_image_tag="cad-analysis:test",
        check_image_digest="sha256:" + "c" * 64,
        brep_sha256="a" * 64,
        step=StepStored(sha256="b" * 64),
        results=parsed.results,
    )
    text = run.model_dump_json()
    assert json.loads(text)["results"][2]["measured"][0] == {
        "name": "volume",
        "value": {"magnitude": 1000.0, "unit": "mm³"},
    }
    assert CheckRun.model_validate_json(text) == run


MISBEHAVIORS = {
    "timed-out": ran(b"", killed=True),
    "out-of-memory": ran(b"", oom=True, exit_code=137),
    "segfault": ran(b"", exit_code=139),
    "empty-stdout": ran(b""),
    "over-the-cap": ran(TooMuchOutput()),
    "not-json": ran(b"not json"),
    "not-an-object": ran(b"[]"),
    "wrong-kind": sent({**good_report(), "kind": "won"}),
    "nonzero-exit-with-a-good-report": ran(json.dumps(good_report()).encode(), exit_code=1),
    "ids-out-of-order": sent({**good_report(), "results": good_report()["results"][::-1]}),
    "a-missing-id": sent({**good_report(), "results": good_report()["results"][:2]}),
    "a-duplicated-id": sent(
        {**good_report(), "results": [good_report()["results"][0]] * 4},
    ),
    "verdict-ok": sent(with_result(0, verdict="ok")),
    "undeclared-measure": sent(with_result(0, measured=[measured("flux", 1, DIMENSIONLESS)])),
    "wrong-unit": sent(with_result(2, measured=[measured("volume", 1000.0, "m^3")])),
    "nan": sent(with_result(2, measured=[measured("volume", float("nan"), "mm^3")])),
    "infinity": sent(with_result(2, measured=[measured("volume", float("inf"), "mm^3")])),
    "step-not-base64": sent({**good_report(), "step": {"kind": "written", "base64": "@@"}}),
    "step-not-a-string": sent({**good_report(), "step": 7}),
    "step-kind-unknown": sent({**good_report(), "step": {"kind": "elsewhere", "reason": "x"}}),
    "step-missing-without-reason": sent({**good_report(), "step": {"kind": "missing"}}),
}


@pytest.mark.parametrize("seen", MISBEHAVIORS.values(), ids=MISBEHAVIORS.keys())
def test_every_misbehavior_gives_four_unknown_results_and_no_step(
    seen: Ran, request_for_pla: Request
) -> None:
    parsed = parse(seen, request_for_pla, OWN_LIMITS)
    assert [result.check_id for result in parsed.results] == [spec.id for spec in SPECS]
    assert {result.verdict for result in parsed.results} == {Verdict.UNKNOWN}
    reasons = {result.reason for result in parsed.results}
    assert len(reasons) == 1
    (reason,) = reasons
    assert reason and "\n" not in reason
    assert parsed.step == StepMissing(reason=reason)


@pytest.mark.parametrize(
    ("seen", "reason"),
    [
        pytest.param(ran(b"", killed=True), "ran past 60 s and was killed", id="timeout"),
        pytest.param(ran(b"", oom=True, exit_code=137), "ran out of memory (1536 MB)", id="oom"),
        pytest.param(
            ran(b"", exit_code=139), "exited with code 139 before it sent a report", id="exit"
        ),
        pytest.param(ran(b""), "sent no report", id="silent"),
        pytest.param(ran(TooMuchOutput()), "sent more than 64 MiB", id="flood"),
        pytest.param(
            sent({**good_report(), "step": {"kind": "written", "base64": "@@"}}),
            "STEP that is not base64",
            id="step",
        ),
        pytest.param(
            sent(with_result(2, measured=[measured("volume", 1.0, "m^3")])),
            "mass: volume is in 'm^3', not 'mm^3'",
            id="unit",
        ),
    ],
)
def test_the_reason_names_the_cause(seen: Ran, reason: str, request_for_pla: Request) -> None:
    assert reason in parse(seen, request_for_pla, OWN_LIMITS).results[0].reason


def test_a_step_the_container_left_out_keeps_the_verdicts_and_says_why(
    request_for_pla: Request,
) -> None:
    reason = "the STEP is 58392064 bytes, over the 50331000 bytes left in the report"
    parsed = parse(
        sent({**good_report(), "step": {"kind": "missing", "reason": reason}}),
        request_for_pla,
        OWN_LIMITS,
    )
    assert [result.verdict for result in parsed.results] == [Verdict.PASS] * 4
    assert parsed.step == StepMissing(reason=reason)


def test_unknown_results_keep_the_formula_sources_and_version_of_a_real_one(
    request_for_pla: Request,
) -> None:
    parsed = parse(ran(b"", killed=True), request_for_pla, OWN_LIMITS)
    assert [(r.formula, r.sources, r.version) for r in parsed.results] == [
        (spec.formula, spec.sources, spec.version) for spec in SPECS
    ]


@pytest.mark.parametrize(
    "key", ["unobtainium", "prusament-pla ", "PRUSAMENT-PLA", " prusament-pla", ""]
)
def test_a_key_that_is_not_exact_has_an_unknown_density(key: str) -> None:
    density = build_request(key, load_materials()).wire["values"]["density"]
    assert density["kind"] == "unknown"
    assert repr(key) in density["reason"]


def test_a_cited_density_reaches_the_container_in_kg_per_mm3() -> None:
    density = build_request("prusament-pla", load_materials()).wire["values"]["density"]
    assert density["kind"] == "known"
    cited = load_materials().get_material("prusament-pla").density
    assert isinstance(cited, Cited)
    assert density["magnitude"] == pytest.approx(cited.magnitude_in("kg/m^3") / 1e9)


def test_a_table_row_whose_density_is_unknown_never_reaches_the_container_as_a_number() -> None:
    table = MaterialsTable("v1", {"mystery": Material("mystery", "Mystery", *[Unknown()] * 5)})
    request = build_request("mystery", table)
    assert request.wire["values"]["density"] == {
        "kind": "unknown",
        "reason": "the materials table has no density for mystery: it says unknown",
    }
    assert request.reads == {}

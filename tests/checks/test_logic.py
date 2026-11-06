import base64
import math
from dataclasses import dataclass, field

import pytest

from cad.checks.container import closed_solid, interference, mass
from cad.checks.container.check import Subject
from cad.checks.container.kernel import EdgeUses, Shape, Unreadable, VolumeProps
from cad.checks.container.runner import run
from cad.checks.container.wire import (
    DensityKnown,
    DensityUnknown,
    DensityWire,
    FindingWire,
    ResultWire,
)

KNOWN: DensityKnown = {"kind": "known", "kg_per_mm3": 1.24e-6}
UNKNOWN: DensityUnknown = {"kind": "unknown", "reason": "no material with key 'x'"}
UNREADABLE_BREP = b"unreadable"


@dataclass(frozen=True, slots=True)
class FakeShape:
    index: int = 0

    def IsNull(self) -> bool:
        return False


@dataclass(slots=True)
class FakeKernel:
    solid_count: int = 1
    valid: bool = True
    uses: EdgeUses = field(default_factory=lambda: EdgeUses(0, 0))
    props: VolumeProps = field(default_factory=lambda: VolumeProps(1000.0, (1.0, 2.0, 3.0)))
    commons: dict[tuple[int, int], float | None] = field(
        default_factory=dict[tuple[int, int], float | None]
    )
    outside: int = 0
    invalid_raises: bool = False
    step_raises: bool = False

    def read_brep(self, data: bytes) -> Shape | Unreadable:
        return Unreadable("not a BREP") if data == UNREADABLE_BREP else FakeShape()

    def solids(self, shape: Shape) -> tuple[Shape, ...]:
        return tuple(FakeShape(index) for index in range(self.solid_count))

    def is_valid(self, shape: Shape) -> bool:
        if self.invalid_raises:
            raise RuntimeError("BRepCheck exploded\nsecond line")
        return self.valid

    def edge_uses(self, shape: Shape) -> EdgeUses:
        return self.uses

    def outside_solids(self, shape: Shape) -> int:
        return self.outside

    def volume_props(self, shape: Shape) -> VolumeProps:
        return self.props

    def common_volume(self, first: Shape, second: Shape) -> float | None:
        assert isinstance(first, FakeShape) and isinstance(second, FakeShape)
        return self.commons.get((first.index, second.index), 0.0)

    def step_bytes(self, shape: Shape) -> bytes:
        if self.step_raises:
            raise RuntimeError("no STEP")
        return b"STEP bytes"


def subject(kernel: FakeKernel, density: DensityWire = KNOWN) -> Subject:
    return Subject(kernel, FakeShape(), density)


def unreadable(density: DensityWire = KNOWN) -> Subject:
    return Subject(FakeKernel(), Unreadable("not a BREP"), density)


def measured(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


@pytest.mark.parametrize(
    ("solids", "valid", "uses", "verdict"),
    [
        pytest.param(1, True, EdgeUses(0, 0), "pass", id="one-closed-valid-solid"),
        pytest.param(0, True, EdgeUses(2, 0), "fail", id="a-shell-has-no-solid"),
        pytest.param(2, True, EdgeUses(0, 0), "fail", id="two-solids"),
        pytest.param(1, False, EdgeUses(0, 0), "fail", id="invalid"),
        pytest.param(1, True, EdgeUses(4, 0), "fail", id="one-solid-and-a-loose-face"),
        pytest.param(1, True, EdgeUses(0, 1), "fail", id="an-edge-of-three-faces"),
    ],
)
def test_closed_solid_passes_only_on_one_valid_solid_with_no_free_or_over_used_edge(
    solids: int, valid: bool, uses: EdgeUses, verdict: str
) -> None:
    found = closed_solid.run(subject(FakeKernel(solid_count=solids, valid=valid, uses=uses)))
    assert found["verdict"] == verdict, found["reason"]


def test_closed_solid_fails_one_solid_beside_a_closed_shell() -> None:
    found = closed_solid.run(subject(FakeKernel(outside=1)))
    assert found["verdict"] == "fail"
    assert measured(found)["shapes_outside_solids"] == 1


def test_closed_solid_reason_names_every_failing_term() -> None:
    kernel = FakeKernel(solid_count=0, valid=False, uses=EdgeUses(2, 1), outside=1)
    found = closed_solid.run(subject(kernel))
    assert found["reason"] == (
        "found 0 solids; exactly 1 is required; 1 shells, faces, edges or vertices lie outside "
        "any solid; BRepCheck_Analyzer calls the shape invalid; 2 edges are used by one face; "
        "1 edges are used by more than two faces"
    )
    assert measured(found) == {
        "solids": 0,
        "shapes_outside_solids": 1,
        "free_edges": 2,
        "over_used_edges": 1,
        "valid": 0,
    }


def test_closed_solid_fails_an_unreadable_brep_and_says_why() -> None:
    found = closed_solid.run(unreadable())
    assert (found["verdict"], found["reason"]) == ("fail", "the BREP could not be read: not a BREP")


def test_interference_reports_every_interfering_pair_not_the_first() -> None:
    kernel = FakeKernel(solid_count=3, commons={(0, 1): 5.0, (1, 2): 7.0})
    found = interference.run(subject(kernel))
    assert found["verdict"] == "fail"
    assert measured(found) == {
        "bodies": 3,
        "interfering_pairs": 2,
        "max_common_volume": 7.0,
        "common_volume:0-1": 5.0,
        "common_volume:1-2": 7.0,
    }
    assert found["reason"] == "solids 0 and 1 share 5 mm^3; solids 1 and 2 share 7 mm^3"


@pytest.mark.parametrize(
    ("common", "verdict"), [(0.001, "pass"), (0.0011, "fail"), (0.0, "pass"), (125.0, "fail")]
)
def test_interference_threshold_is_inclusive_at_a_thousandth_of_a_cubic_millimetre(
    common: float, verdict: str
) -> None:
    found = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): common})))
    assert found["verdict"] == verdict


def test_interference_of_one_solid_passes_with_one_body() -> None:
    found = interference.run(subject(FakeKernel(solid_count=1)))
    assert (found["verdict"], measured(found)["bodies"]) == ("pass", 1)


def test_interference_cannot_pass_a_shape_with_no_solid_or_an_undone_boolean() -> None:
    assert interference.run(subject(FakeKernel(solid_count=0)))["verdict"] == "unknown"
    undone = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): None})))
    assert (undone["verdict"], undone["reason"]) == (
        "unknown",
        "solids 0 and 1 could not be intersected",
    )
    assert interference.run(unreadable())["verdict"] == "unknown"


def test_interference_cannot_pass_a_pair_whose_common_volume_is_not_a_number() -> None:
    found = interference.run(subject(FakeKernel(solid_count=2, commons={(0, 1): math.nan})))
    assert (found["verdict"], found["reason"]) == (
        "unknown",
        "solids 0 and 1 could not be intersected",
    )


def test_interference_names_an_undone_pair_beside_a_real_overlap() -> None:
    kernel = FakeKernel(solid_count=3, commons={(0, 1): 5.0, (0, 2): None})
    found = interference.run(subject(kernel))
    assert found["verdict"] == "fail"
    assert found["reason"].endswith("solids 0 and 2 could not be intersected")


def test_mass_multiplies_the_volume_by_the_density_it_was_given() -> None:
    found = mass.run(subject(FakeKernel(props=VolumeProps(2000.0, (1.0, 2.0, 3.0)))))
    assert found["verdict"] == "pass"
    assert measured(found) == {
        "volume": 2000.0,
        "center_of_mass:x": 1.0,
        "center_of_mass:y": 2.0,
        "center_of_mass:z": 3.0,
        "density": 1.24e-6,
        "mass": 2000.0 * 1.24e-6,
    }


def test_mass_never_guesses_a_density() -> None:
    found = mass.run(subject(FakeKernel(), UNKNOWN))
    assert (found["verdict"], found["reason"]) == ("unknown", UNKNOWN["reason"])
    assert sorted(measured(found)) == [
        "center_of_mass:x",
        "center_of_mass:y",
        "center_of_mass:z",
        "volume",
    ]


@pytest.mark.parametrize("volume", [0.0, -5.0, math.nan, math.inf])
def test_mass_fails_a_volume_that_is_not_positive_and_finite(volume: float) -> None:
    kernel = FakeKernel(props=VolumeProps(volume, (0.0, 0.0, 0.0)))
    assert mass.run(subject(kernel))["verdict"] == "fail"


def test_mass_of_an_unreadable_brep_is_unknown_never_pass() -> None:
    assert mass.run(unreadable())["verdict"] == "unknown"


def by_id(results: list[ResultWire]) -> dict[str, ResultWire]:
    return {result["id"]: result for result in results}


def test_a_check_that_raises_becomes_unknown_and_the_others_still_run() -> None:
    report = run({"density": KNOWN}, b"brep", FakeKernel(invalid_raises=True))
    results = by_id(report["results"])
    assert results["closed_solid"]["verdict"] == "unknown"
    assert (
        results["closed_solid"]["reason"] == "closed_solid raised RuntimeError: BRepCheck exploded"
    )
    assert (results["interference"]["verdict"], results["mass"]["verdict"]) == ("pass", "pass")


def test_the_report_lists_every_check_in_suite_order_with_the_step_of_the_measured_shape() -> None:
    report = run({"density": KNOWN}, b"brep", FakeKernel())
    assert [result["id"] for result in report["results"]] == [
        "closed_solid",
        "interference",
        "mass",
    ]
    assert report["step"] is not None
    assert base64.b64decode(report["step"]) == b"STEP bytes"


def test_an_unreadable_brep_still_reports_all_three_checks_and_no_step() -> None:
    report = run({"density": KNOWN}, UNREADABLE_BREP, FakeKernel())
    verdicts = {result["id"]: result["verdict"] for result in report["results"]}
    assert verdicts == {"closed_solid": "fail", "interference": "unknown", "mass": "unknown"}
    assert report["step"] is None


def test_a_step_that_cannot_be_written_leaves_the_checks_standing() -> None:
    report = run({"density": KNOWN}, b"brep", FakeKernel(step_raises=True))
    assert report["step"] is None
    assert {result["verdict"] for result in report["results"]} == {"pass"}

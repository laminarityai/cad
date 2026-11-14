from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from cad.checks.container import fea, lone
from cad.checks.container.calculix import Material, NodalField, NodalLoads, SolveFailed
from cad.checks.container.check import BodyPart, Subject
from cad.checks.container.inputs import Inputs
from cad.checks.container.kernel import Shape, Unreadable, ocp_kernel
from cad.checks.container.mesher import MeshFailed, TetMesh
from cad.checks.container.wire import (
    FindingWire,
    LoadCaseWire,
    MeasuredWire,
    ResultWire,
    ValueWire,
)
from tests.support.solids import box, compound, cut, through_hole

KERNEL = ocp_kernel()
CASE: LoadCaseWire = {
    "support": {"kind": "flat_end"},
    "load": {"kind": "far_end", "force_n": 10.0, "direction": {"kind": "any"}},
}
PASSED: dict[str, ResultWire] = {
    one: {"id": one, "verdict": "pass", "measured": [], "reason": "ok"}
    for one in ("closed_solid", "interference")
}
BLOCK = cut(box(20, 20, 5), through_hole(5, 10, 10))
BEAM = box(100, 10, 5, at=(20, 5, 0))
GEARS = box(10, 10, 5, at=(0, 40, 0))
type Values = dict[str, float]
CARBON: Values = {"elastic_modulus": 70_000.0, "poisson_ratio": 0.3}
STEEL: Values = {"elastic_modulus": 200_000.0, "poisson_ratio": 0.29}
MESHED_NOTHING = "this test meshes nothing"


def values(made: Values) -> dict[str, ValueWire]:
    return {name: {"kind": "known", "magnitude": value} for name, value in made.items()}


def part(
    name: str, solids: tuple[int, ...], made: dict[str, float], case: LoadCaseWire
) -> BodyPart:
    return BodyPart(name, solids, Inputs(fea.TAKES, values(made), (case,)))


@dataclass
class Recording:
    """Meshes nothing, and keeps the BREP each lone solid was handed over as."""

    breps: list[bytes] = field(default_factory=list[bytes])

    def mesh(self, size_mm: float, floor_mm: float) -> TetMesh | MeshFailed:
        return MeshFailed(MESHED_NOTHING)

    def solve(
        self,
        mesh: TetMesh,
        material: Material,
        fixed: frozenset[int],
        unit_loads: Sequence[NodalLoads],
    ) -> tuple[NodalField, ...] | SolveFailed:
        raise NotImplementedError(MESHED_NOTHING)

    def alone(self, brep: bytes) -> "Recording":
        self.breps.append(brep)
        return self


def checked(case: LoadCaseWire, fem: Recording | None = None) -> FindingWire:
    shape = compound(BLOCK, BEAM, GEARS)
    bodies = (
        part("block", (0,), CARBON, case),
        part("beam", (1,), STEEL, case),
        part("gear", (2, 2), STEEL, case),
    )
    inputs = Inputs(fea.TAKES, {}, (case,))
    subject = Subject(KERNEL, fem or Recording(), shape, inputs, PASSED, bodies=bodies)
    return fea.run(subject)


def on(body: str) -> LoadCaseWire:
    return {**CASE, "body": body}


def by_name(found: FindingWire) -> dict[str, float]:
    return {one["name"]: one["magnitude"] for one in found["measured"]}


def test_a_load_case_that_names_no_body_on_several_solids_is_unknown_and_says_to_name_one() -> None:
    found = checked(CASE)
    assert (found["verdict"], found["measured"]) == ("unknown", [])
    assert "names no body" in found["reason"]
    assert lone.NAME_ONE in found["reason"]


def test_a_load_case_on_a_body_the_variant_lacks_is_unknown_and_names_it() -> None:
    found = checked(on("lid"))
    assert found["verdict"] == "unknown"
    assert found["reason"] == "the variant holds no body named lid, so no stress was solved"


def test_a_load_case_on_a_body_of_several_solids_is_unknown_and_says_to_name_one_solid() -> None:
    found = checked(on("gear"))
    assert found["verdict"] == "unknown"
    assert found["reason"] == f"the body gear has 2 solids; {lone.NAME_ONE}"


def test_the_named_body_alone_is_meshed_in_its_own_material() -> None:
    fem = Recording()
    found = checked(on("beam"), fem)
    (brep,) = fem.breps
    read = KERNEL.read_brep(brep)
    assert not isinstance(read, Unreadable)
    (solid,) = KERNEL.solids(read)
    assert KERNEL.volume_props(solid).volume == pytest.approx(100 * 10 * 5)
    assert found["verdict"] == "unknown"
    assert found["reason"].startswith("solved the body beam alone, in its own material: ")
    assert found["reason"].endswith(MESHED_NOTHING)
    assert by_name(found)["elastic_modulus:beam"] == STEEL["elastic_modulus"]
    assert by_name(found)["poisson_ratio:beam"] == STEEL["poisson_ratio"]


def picked(body: str) -> lone.Lone:
    shape = compound(BLOCK, BEAM, GEARS)
    bodies = (part("block", (0,), CARBON, CASE), part("beam", (1,), STEEL, CASE))
    subject = Subject(KERNEL, Recording(), shape, Inputs(fea.TAKES, {}), PASSED, bodies=bodies)
    found = lone.alone(subject, shape, body)
    assert isinstance(found, lone.Lone)
    return found


def faces_of(shape: Shape) -> int:
    return len(KERNEL.faces(shape))


def test_the_lone_solid_s_faces_follow_the_faces_of_the_solids_before_it() -> None:
    assert picked("block").offset == 0
    beam = picked("beam")
    assert beam.offset == faces_of(BLOCK) == 7
    whole = KERNEL.faces(compound(BLOCK, BEAM, GEARS))
    own = KERNEL.faces(beam.shape)
    shifted = whole[beam.offset : beam.offset + len(own)]
    assert [list(one.centroid) for one in shifted] == [list(one.centroid) for one in own]


def test_a_lone_solve_s_faces_and_echoed_values_are_named_as_the_variant_s() -> None:
    echo: MeasuredWire = {"name": "elastic_modulus", "magnitude": 2e5, "unit": "MPa"}
    factor: MeasuredWire = {"name": "safety_factor", "magnitude": 3.0, "unit": "dimensionless"}
    solved: FindingWire = {
        "verdict": "pass",
        "measured": [echo, factor],
        "reason": "solved",
        "where": {"support": [0], "load": [3], "displacement": {"support": [0], "load": [5]}},
    }
    found = lone.placed(solved, picked("beam"), fea.READS)
    assert found["measured"] == [{**echo, "name": "elastic_modulus:beam"}, factor]
    assert found.get("where") == {
        "support": [7],
        "load": [10],
        "displacement": {"support": [7], "load": [12]},
    }
    assert found["reason"] == "solved the body beam alone, in its own material: solved"


def test_a_case_on_one_solid_with_no_body_is_solved_as_it_always_was() -> None:
    shape = BEAM
    subject = Subject(KERNEL, Recording(), shape, Inputs(fea.TAKES, {}), PASSED)
    found = lone.alone(subject, shape, None)
    assert isinstance(found, lone.Lone)
    assert (found.subject, found.shape, found.offset) == (subject, shape, 0)
    solved: FindingWire = {"verdict": "pass", "measured": [], "reason": "solved"}
    assert lone.placed(solved, found, fea.READS) is solved

import math
import time

import pytest

from cad.context_parts.ingest import Brep, Ingested, NotAPart, StepFile, ingest, judged
from cad.sandbox.container import Attended, ContainerState, Job, Ran, TooMuchOutput
from tests.support.part_files import step_bytes
from tests.support.solids import (
    box,
    box_face,
    box_shell,
    brep_bytes,
    compound,
    cut,
    inside_out,
    loosened,
    through_hole,
)

pytestmark = pytest.mark.docker

JOB = Job("check", "sha256:analysis", (), b"")
SOURCE = Brep(b"a variant")


def ingested(brep: bytes) -> Ingested:
    found = ingest(Brep(brep))
    assert isinstance(found, Ingested), found
    return found


def test_a_box_reports_its_solid_volume_and_corners() -> None:
    found = ingested(brep_bytes(box(30, 10, 20, at=(1, 2, -3)))).facts
    assert found.solids == 1
    assert found.volume_mm3 == pytest.approx(6000, rel=1e-9)
    assert found.box_min == pytest.approx((1, 2, -3), abs=1e-9)
    assert found.box_max == pytest.approx((31, 12, 17), abs=1e-9)


def test_two_solids_are_one_part_of_two_solids() -> None:
    found = ingested(brep_bytes(compound(box(10, 10, 10), box(5, 5, 5, at=(20, 0, 0))))).facts
    assert (found.solids, found.volume_mm3) == (2, pytest.approx(1125, rel=1e-9))
    assert found.box_max == pytest.approx((25, 10, 10), abs=1e-9)


@pytest.mark.parametrize(
    ("brep", "reason"),
    [
        pytest.param(brep_bytes(box_shell(10, 10, 10)), "the shape has no solid", id="shell"),
        pytest.param(brep_bytes(box_face(10, 10, 10)), "the shape has no solid", id="face"),
        pytest.param(
            brep_bytes(compound(box(10, 10, 10), box_face(5, 5, 5))),
            "the shape has 1 shells, faces, edges or vertices outside any solid",
            id="solid-and-loose-face",
        ),
        pytest.param(
            brep_bytes(loosened(box(10, 10, 10), 0.01)),
            "the shape has a tolerance of 0.01 mm, over the 0.001 mm limit",
            id="loose-tolerance",
        ),
        pytest.param(
            brep_bytes(inside_out(box(10, 10, 10))),
            "the shape has solids with a volume of 0 or less, inside out or empty: 0",
            id="inside-out",
        ),
        pytest.param(
            brep_bytes(compound(box(20, 20, 20), inside_out(box(5, 5, 5, at=(2, 2, 2))))),
            "the shape has solids with a volume of 0 or less, inside out or empty: 1",
            id="inside-out-within-a-good-solid",
        ),
        pytest.param(b"not a BREP", "the BREP cannot be read", id="unreadable"),
    ],
)
def test_a_shape_that_is_not_whole_solids_is_not_a_part(brep: bytes, reason: str) -> None:
    found = ingest(Brep(brep))
    assert isinstance(found, NotAPart), found
    assert found.reason.startswith(reason), found.reason


def ran(report: bytes | TooMuchOutput, code: int = 0, *, oom: bool = False) -> Ran:
    state = ContainerState(Status="exited", ExitCode=code, OOMKilled=oom, Error="")
    return Ran(Attended(killed_at_deadline=False, report=report, output=""), state)


MALFORMED = "reading the part sent a malformed report"
NAN = (
    b'{"kind": "part", "solids": 1, "volume_mm3": NaN, "box_min": [0, 0, 0], "box_max": [1, 1, 1]}'
)
KILLED = Ran(
    Attended(killed_at_deadline=True, report=b"", output=""),
    ContainerState(Status="exited", ExitCode=137, OOMKilled=False, Error=""),
)


@pytest.mark.parametrize(
    ("outcome", "reason"),
    [
        pytest.param(KILLED, "reading the part ran past 60 s and was stopped", id="timed-out"),
        pytest.param(
            ran(b"", 137, oom=True), "reading the part ran out of memory (2048 MB)", id="oom"
        ),
        pytest.param(
            ran(b"", 1), "reading the part exited with code 1 before it reported", id="died"
        ),
        pytest.param(
            ran(TooMuchOutput()),
            "reading the part sent more output than a report holds",
            id="flood",
        ),
        pytest.param(ran(b""), MALFORMED, id="silent"),
        pytest.param(ran(b'{"kind": "part", "solids": 1}'), MALFORMED, id="short"),
        pytest.param(ran(NAN), MALFORMED, id="nan"),
    ],
)
def test_a_container_that_does_not_report_facts_is_not_a_part(outcome: Ran, reason: str) -> None:
    assert judged(outcome, JOB, SOURCE) == NotAPart(reason)


def test_a_brep_keeps_its_own_bytes_and_a_step_round_trips_through_the_container() -> None:
    plate = cut(box(40, 20, 10), through_hole(6, 20, 10, depth=10))
    own = brep_bytes(plate)
    assert ingested(own).brep == own

    started = time.monotonic()
    found = ingest(StepFile(step_bytes(compound(plate, box(5, 5, 5, at=(60, 0, 0))))))
    seconds = time.monotonic() - started
    assert isinstance(found, Ingested), found
    assert (found.facts.solids, len(found.facts.holes)) == (2, 1)
    assert found.facts.holes[0].diameter_mm == pytest.approx(6, abs=1e-6)
    assert found.facts.volume_mm3 == pytest.approx(8000 - 90 * math.pi + 125, rel=1e-6)
    assert found.brep != own
    assert seconds < 60, seconds

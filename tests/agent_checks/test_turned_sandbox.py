"""Repeat and turn in real sandbox containers: write_check runs the geometry code on the probe
shapes, plain and turned, and a scored variant runs it on the stored part, plain and turned by a
team-only container."""

from datetime import date

import pytest

from cad.agent_checks import harness, turned
from cad.agent_checks.store import CheckRefused, StoredCheck
from cad.agent_checks.write import write_check
from cad.records.roots import Roots
from cad.sandbox import builder, image
from tests.support.agent_checks import BOUNDING_BOX, fetching, snap_fit, unchecked_brief

pytestmark = pytest.mark.docker

RANDOM = """
import random
v = random.uniform(1, 9)
report("h", v, "mm"); report("l", 10 * v, "mm"); report("y", v / 2, "mm")
"""
HASH_ORDER = """
v = 1 + hash("snap arm") % 1000003
report("h", v, "mm"); report("l", 10 * v, "mm"); report("y", v / 2, "mm")
"""
CONSTANT = 'report("h", 2.0, "mm"); report("l", 20.0, "mm"); report("y", 1.0, "mm")'
FOREVER = "while True:\n    pass"


def write(roots: Roots, geometry: str) -> StoredCheck:
    brief_id, requirement_id = unchecked_brief(roots)
    return write_check(
        roots,
        brief_id,
        requirement_id,
        snap_fit(geometry=geometry),
        fetcher=fetching(),
        today=lambda: date(2026, 11, 12),
    )


def arm() -> bytes:
    """A snap arm 20 mm long, 5 mm wide and 2 mm thick, built by team code."""
    tag = image.image_tag(image.BUILD)
    code = "from build123d import *\nresult = Box(20, 5, 2)\n"
    ran = builder.build(code, image.current_image(tag), wall_seconds=60)
    assert isinstance(ran.verdict, builder.Artifacts)
    return ran.verdict.brep


def test_geometry_read_from_the_shape_passes_repeat_and_turn(roots: Roots) -> None:
    assert write(roots, snap_fit().geometry or "").number == 1


@pytest.mark.parametrize(
    ("geometry", "reason"),
    [
        (BOUNDING_BOX, "different answers when the part was turned and moved"),
        (RANDOM, "different answers when the part was turned and moved"),
        (HASH_ORDER, "different answers when the part was turned and moved"),
        (CONSTANT, "gave h = 2 mm on each of"),
    ],
    ids=["bounding-box", "random", "hash-order", "constant"],
)
def test_geometry_the_turn_or_the_probes_expose_is_refused(
    roots: Roots, geometry: str, reason: str
) -> None:
    with pytest.raises(CheckRefused, match=reason):
        write(roots, geometry)
    assert not list(roots.projects.glob("*/agent_checks/*.signed"))


def test_geometry_that_never_ends_is_refused_at_the_wall_limit(
    roots: Roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "WALL_SECONDS", 5)
    with pytest.raises(CheckRefused, match=r"no values on any probe shape.*timed out after 5 s"):
        write(roots, FOREVER)


@pytest.mark.usefixtures("no_sandbox")
def test_a_turned_variant_reads_the_same_values_as_the_stored_one(roots: Roots) -> None:
    [measured] = turned.on_variant(arm(), [write(roots, snap_fit().geometry or "").check])
    assert not isinstance(measured, turned.Unmeasured | turned.Unsound)
    assert {name: float(value.m_as("mm")) for name, value in measured.items()} == pytest.approx(  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        {"h": 2.0, "l": 20.0, "y": 1.0}
    )


@pytest.mark.usefixtures("no_sandbox")
def test_code_that_reads_orientation_on_a_variant_decides_nothing(roots: Roots) -> None:
    """The probe gate is skipped, as code written to fool it would pass it: the variant's turn,
    made where the agent's code never runs, still catches the bounding box."""
    [measured] = turned.on_variant(arm(), [write(roots, BOUNDING_BOX).check])
    assert isinstance(measured, turned.Unsound)
    assert "different answers when the part was turned and moved" in measured.reason


@pytest.mark.usefixtures("no_sandbox")
def test_code_that_never_ends_on_a_variant_is_unmeasured(
    roots: Roots, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = write(roots, FOREVER).check
    monkeypatch.setattr(harness, "WALL_SECONDS", 5)
    [measured] = turned.on_variant(arm(), [check])
    assert measured == turned.Unmeasured("timed out after 5 s")

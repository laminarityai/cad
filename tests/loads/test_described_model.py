import itertools

import pytest
from pydantic import ValidationError

from cad.checks.container.terms import of_wire
from cad.loads.model import LoadCase
from cad.loads.words import describe_case
from tests.support.load_cases import (
    CASE,
    DIRECTIONS,
    LOADS,
    SUPPORTS,
    Part,
    case,
    hole_hook,
    parse,
    shelf,
)


def accepted() -> list[tuple[str, str, str]]:
    """Every pairing of a support, a load and a direction that parses."""
    found: list[tuple[str, str, str]] = []
    for support, load, direction in itertools.product(SUPPORTS, LOADS, DIRECTIONS):
        try:
            parse(SUPPORTS[support], LOADS[load], DIRECTIONS[direction])
        except ValidationError:
            continue
        found.append((support, load, direction))
    return found


def test_a_reviewed_phrase_is_not_described_and_a_new_term_is() -> None:
    assert not CASE.validate_python(hole_hook()).described
    assert CASE.validate_python(shelf()).described


@pytest.mark.parametrize("support", ["end_of_middle", "facing", "each_hole", "in_one_flat_face"])
def test_each_new_support_makes_a_case_described(support: str) -> None:
    far_end = LOADS["far_end"]
    assert parse(SUPPORTS[support], far_end, DIRECTIONS["any"]).described


@pytest.mark.parametrize("load", ["on_largest_flat", "on_farthest_hole", "on_farthest_inner_curve"])
def test_each_new_load_makes_a_case_described(load: str) -> None:
    assert parse(SUPPORTS["holes"], LOADS[load], DIRECTIONS["any"]).described


@pytest.mark.parametrize("direction", ["into", "away"])
def test_each_new_direction_makes_a_case_described(direction: str) -> None:
    load = LOADS["on_largest_flat"] if direction == "into" else LOADS["far_end"]
    assert parse(SUPPORTS["holes"], load, DIRECTIONS[direction]).described


@pytest.mark.parametrize(
    ("support", "load", "direction"),
    [
        pytest.param("holes", "on_opposite", "into", id="on_opposite_needs_a_facing_support"),
        pytest.param("facing", "far_end", "into", id="into_needs_a_flat_face_load"),
        pytest.param("holes", "far_end", "into", id="into_on_the_far_end"),
        pytest.param("holes", "on_farthest_hole", "into", id="into_on_a_hole"),
        pytest.param(
            "largest_flat", "on_largest_flat", "across_hole_axis", id="hole_axis_on_a_flat"
        ),
        pytest.param("end_of_middle", "far_end", "along_hole_axis", id="hole_axis_on_an_end"),
        pytest.param("facing", "on_opposite", "across_hole_axis", id="hole_axis_on_facing"),
        pytest.param(
            "each_inner_curve",
            "on_farthest_inner_curve",
            "along_hole_axis",
            id="hole_axis_on_curve",
        ),
    ],
)
def test_a_pairing_that_names_nothing_is_refused(support: str, load: str, direction: str) -> None:
    with pytest.raises(ValidationError):
        parse(SUPPORTS[support], LOADS[load], DIRECTIONS[direction])


@pytest.mark.parametrize("support", ["holes", "each_hole", "in_one_flat_face"])
def test_the_hole_axis_is_allowed_when_the_support_goes_through_holes(support: str) -> None:
    parse(SUPPORTS[support], LOADS["far_end"], DIRECTIONS["across_hole_axis"])


def test_a_reviewed_pairing_stored_before_still_reads() -> None:
    """The container answers unknown for it, as before, so the host does not refuse it."""
    stored = parse(SUPPORTS["largest_flat"], LOADS["far_end"], DIRECTIONS["across_hole_axis"])
    assert not stored.described


def test_a_facing_pair_pressed_into_the_opposite_face_parses() -> None:
    assert parse(SUPPORTS["facing"], LOADS["on_opposite"], DIRECTIONS["into"]).described


def test_a_described_case_crosses_the_wire_with_millimetres_and_newtons() -> None:
    wire = CASE.validate_python(shelf({"magnitude": 0.049, "unit": "kN"})).wire()
    assert wire == {
        "support": {"kind": "in_one_flat_face", "count": 2, "diameter_mm": 5.5},
        "load": {
            "kind": "on_largest_flat",
            "middle": True,
            "force_n": 49.0,
            "direction": {"kind": "into"},
        },
    }


def test_a_new_force_on_a_described_case_shares_its_unit_case() -> None:
    heavier = CASE.validate_python(shelf({"magnitude": 98.0, "unit": "N"}))
    assert heavier.unit_case == CASE.validate_python(shelf()).unit_case
    assert heavier.id != CASE.validate_python(shelf()).id


def test_a_term_outside_the_list_is_refused() -> None:
    with pytest.raises(ValidationError):
        CASE.validate_python(
            case({"kind": "on_a_face", "name": "f12"}, LOADS["far_end"], {"kind": "any"})
        )


def test_no_two_pairings_read_alike_and_none_reads_as_a_reviewed_phrase() -> None:
    reviewed: dict[str, tuple[str, str, str]] = {}
    described: dict[str, tuple[str, str, str]] = {}
    for key in accepted():
        words = describe_case(parse(SUPPORTS[key[0]], LOADS[key[1]], DIRECTIONS[key[2]]))
        loaded: LoadCase = parse(SUPPORTS[key[0]], LOADS[key[1]], DIRECTIONS[key[2]])
        book = described if loaded.described else reviewed
        assert words not in reviewed and words not in described, (key, words)
        book[words] = key
    assert len(reviewed) >= 6
    assert len(described) >= 100


def test_the_words_name_what_each_term_runs() -> None:
    words = describe_case(CASE.validate_python(shelf()))
    assert words == (
        "49 N on the middle of its largest flat face, pressing into the face; "
        "held by fixing the bores of exactly 2 holes of 5.5 mm that open on one flat face, "
        "whichever face is worse"
    )
    pulled = parse(SUPPORTS["each_hole"], LOADS["on_farthest_hole"], DIRECTIONS["away"])
    assert "fixing the bore of one hole of 5.5 mm, whichever is worse" in describe_case(pulled)
    assert "pulling straight away from the supports" in describe_case(pulled)


def test_parts_of_a_case_can_be_read_back() -> None:
    parts: list[Part] = [hole_hook(), shelf()]
    for part in parts:
        loaded = CASE.validate_python(part)
        assert CASE.validate_python(CASE.dump_python(loaded, mode="json")) == loaded


def _class_of(kind: str) -> str:
    return "AnyWay" if kind == "any" else "".join(word.title() for word in kind.split("_"))


def test_every_accepted_pairing_parses_in_the_container_as_the_same_terms() -> None:
    """The host and the container must agree on every kind, or a check reads another case."""
    for support, load, direction in accepted():
        loaded = parse(SUPPORTS[support], LOADS[load], DIRECTIONS[direction])
        parsed = of_wire(loaded.wire())
        assert type(parsed.support).__name__ == _class_of(loaded.support.kind)
        assert type(parsed.load).__name__ == _class_of(loaded.load.kind)
        assert type(parsed.direction).__name__ == _class_of(loaded.load.direction.kind)

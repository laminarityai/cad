from cad.sandbox.outcome import AREAS, MAX_AREA_FACES, MAX_AREAS, MAX_FACE_NUMBER

LINUX_ARGUMENT_BYTES = 131_072


def test_the_largest_areas_a_build_may_report_fit_one_container_argument() -> None:
    each = MAX_AREA_FACES // MAX_AREAS
    top = MAX_FACE_NUMBER - MAX_AREA_FACES
    largest = AREAS.validate_python(
        [
            {
                "name": chr(0x1F600 + n) * 60,
                "colour": "#1a1a1a",
                "faces": list(range(top + n * each, top + (n + 1) * each)),
            }
            for n in range(MAX_AREAS)
        ]
    )
    assert sum(len(area.faces) for area in largest) == MAX_AREA_FACES
    assert len(AREAS.dump_json(largest)) < LINUX_ARGUMENT_BYTES

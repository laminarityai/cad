"""Recall on a ten-source corpus of the kind the agent will ask about, and near misses.

`recall_corpus/` holds the ten sources. Its keys follow one convention per heading, and none was
written after reading HELD_OUT. `near_miss_corpus/` adds the family or sibling unit that each
near-miss query is really about, so the right answer and the near miss compete in one ranking.
"""

import shutil
from pathlib import Path

import pytest

from cad.knowledge.corpus import load
from cad.knowledge.search import Index

HERE = Path(__file__).parent
RECALL_CORPUS = HERE / "recall_corpus"
NEAR_MISS_CORPUS = HERE / "near_miss_corpus"

AUTHORED = [
    ("Bambu PLA Basic density", "bambu-pla-basic#density"),
    ("Bambu Lab PLA Basic density", "bambu-pla-basic#density"),
    ("density of Bambu PLA Basic", "bambu-pla-basic#density"),
    ("Bambu PLA Basic heat deflection temperature", "bambu-pla-basic#heat-deflection-temperature"),
    ("Bambu Lab PLA Matte density", "bambu-pla-matte#density"),
    ("Bambu PLA Matte density", "bambu-pla-matte#density"),
    ("Bambu Lab PETG HF density", "bambu-petg-hf#density"),
    ("Bambu PETG HF heat deflection temperature", "bambu-petg-hf#heat-deflection-temperature"),
    ("Bambu PETG HF density", "bambu-petg-hf#density"),
    ("PolyLite ABS density", "polylite-abs#density"),
    ("PolyLite ABS Vicat softening temperature", "polylite-abs#vicat-softening-temperature"),
    ("PolyLite ABS vicat temperature", "polylite-abs#vicat-softening-temperature"),
    ("PolyLite ASA weather resistance", "polylite-asa#weather-resistance"),
    ("PolyLite ASA density", "polylite-asa#density"),
    ("Bambu PA6-CF density", "bambu-pa6-cf#density"),
    ("Bambu PA6-CF drying", "bambu-pa6-cf#drying"),
    ("Bambu PA6 CF density", "bambu-pa6-cf#density"),
    ("NinjaFlex shore hardness", "ninjaflex-tpu#shore-hardness"),
    ("NinjaFlex TPU density", "ninjaflex-tpu#density"),
    ("6061-T6 density", "aluminium-6061#density"),
    ("aluminum 6061-T6 density", "aluminium-6061#density"),
    ("6061-T6 yield strength", "aluminium-6061#yield-strength"),
    ("aluminum 6061-T6 yield strength", "aluminium-6061#yield-strength"),
    ("M5 clearance hole", "iso-273-clearance#clearance-hole-sizes"),
    ("ISO 273 M5 clearance", "iso-273-clearance#clearance-hole-sizes"),
    ("AK Steel 316L density", "stainless-316l#density"),
    ("AK Steel 316L stainless steel density", "stainless-316l#density"),
    ("Bambu PLA Basic HDT", "bambu-pla-basic#heat-deflection-temperature"),
    ("Bambu PETG HF HDT", "bambu-petg-hf#heat-deflection-temperature"),
    ("PolyLite ASA UV resistance", "polylite-asa#weather-resistance"),
    ("Bambu PA6-CF drying temperature", "bambu-pa6-cf#drying"),
    ("M5 clearance hole size", "iso-273-clearance#clearance-hole-sizes"),
    ("PolyLite ABS densities", "polylite-abs#density"),
    ("Bambu PLA Basic density g/cm3", "bambu-pla-basic#density"),
    ("Bambu PLA Basic density at 23 °C", "bambu-pla-basic#density"),
]
HELD_OUT = [
    ("Bambu PLA Basic heat deflection", "bambu-pla-basic#heat-deflection-temperature"),
    ("PolyLite ABS specific gravity", "polylite-abs#density"),
    ("NinjaFlex TPU hardness", "ninjaflex-tpu#shore-hardness"),
    ("aluminium 6061-T6 density", "aluminium-6061#density"),
    ("6061-T6 tensile yield", "aluminium-6061#yield-strength"),
    ("Bambu PA6-CF drying time", "bambu-pa6-cf#drying"),
    ("Bambu PETG HF HDT temperature", "bambu-petg-hf#heat-deflection-temperature"),
    ("M4 clearance hole diameter", "iso-273-clearance#clearance-hole-sizes"),
    ("AK Steel 316L density g/cm3", "stainless-316l#density"),
    ("PolyLite ASA UV", "polylite-asa#weather-resistance"),
    ("PolyLite ABS vicat", "polylite-abs#vicat-softening-temperature"),
    ("Bambu PLA Matte density?", "bambu-pla-matte#density"),
]
NEAR_MISSES = [
    ("PLA density", "pla#density", "bambu-pla-basic#density"),
    ("PLA Basic density", "bambu-pla-basic#density", "bambu-pla-matte#density"),
    (
        "PLA Basic HDT",
        "bambu-pla-basic#heat-deflection-temperature",
        "pla#heat-deflection-temperature",
    ),
    ("PLA Matte density", "bambu-pla-matte#density", "bambu-pla-basic#density"),
    ("PETG HF density", "bambu-petg-hf#density", "petg#density"),
    ("PA6-CF density", "bambu-pa6-cf#density", "pa6#density"),
    ("PA6-CF drying", "bambu-pa6-cf#drying", "pa6#drying"),
    ("316L density", "stainless-316l#density", "stainless-304#density"),
    ("316L stainless steel density", "stainless-316l#density", "stainless-304#density"),
    ("stainless steel 316L density", "stainless-316l#density", "stainless-304#density"),
    ("TPU shore hardness", "tpu#shore-hardness", "ninjaflex-tpu#shore-hardness"),
    ("ABS density", "abs#density", "polylite-abs#density"),
    ("ASA density", "asa#density", "polylite-asa#density"),
    ("TPU density", "tpu#density", "ninjaflex-tpu#density"),
    ("PETG density", "petg#density", "bambu-petg-hf#density"),
    ("PA6 density", "pa6#density", "bambu-pa6-cf#density"),
    ("PLA Silk density", "bambu-pla-silk#density", "bambu-pla-matte#density"),
    ("TPU 95A shore hardness", "tpu-95a#shore-hardness", "ninjaflex-tpu#shore-hardness"),
    ("ABS UV resistance", "abs#weather-resistance", "polylite-asa#weather-resistance"),
    ("aluminum 7075-T6 density", "aluminium-7075#density", "aluminium-6061#density"),
    ("304 stainless steel density", "stainless-304#density", "stainless-316l#density"),
    ("steel density", "steel#density", "stainless-316l#density"),
]
"""(query, the unit it is about, the near miss the old design feared)."""
NO_RIGHT_UNIT = [
    "6061 yield strength",
    "6061 density",
    "Polymaker ABS density",
    "nylon drying",
    "NinjaFlex 95A shore hardness",
    "Bambu density",
    "M8 clearance hole",
]
"""Near misses whose subject no unit is about: a temper left out, a group name, a missing size."""


def ranked(index: Index, query: str, k: int = 5) -> list[str]:
    return [hit.pointer.id.removeprefix("kb:") for hit in index.search(query, k)]


def recall_at(index: Index, asked: list[tuple[str, str]], k: int) -> int:
    return sum(1 for query, expected in asked if expected in ranked(index, query, k))


@pytest.fixture(scope="module")
def index() -> Index:
    return Index(load(RECALL_CORPUS))


@pytest.fixture(scope="module")
def crowded(tmp_path_factory: pytest.TempPathFactory) -> Index:
    directory = tmp_path_factory.mktemp("crowded")
    for path in [*RECALL_CORPUS.glob("*.md"), *NEAR_MISS_CORPUS.glob("*.md")]:
        shutil.copy(path, directory / path.name)
    return Index(load(directory))


def test_the_authors_questions_find_their_unit_first(index: Index) -> None:
    # The exact-identity design found 33/35.
    assert recall_at(index, AUTHORED, 1) == len(AUTHORED)


def test_held_out_paraphrases_find_their_unit_first(index: Index) -> None:
    # The exact-identity design found 3/12 here, the clean figure without the leaked keys.
    assert recall_at(index, HELD_OUT, 1) == len(HELD_OUT)


def test_recall_holds_when_the_near_misses_are_in_the_corpus(crowded: Index) -> None:
    # "Bambu PLA Basic density at 23 °C" ranks the HDT section first: its quote has "°C".
    assert recall_at(crowded, AUTHORED, 1) >= 34
    assert recall_at(crowded, AUTHORED, 5) == len(AUTHORED)
    assert recall_at(crowded, HELD_OUT, 1) == len(HELD_OUT)


@pytest.mark.parametrize(("query", "right", "near"), NEAR_MISSES)
def test_the_unit_a_query_is_about_outranks_its_near_miss(
    crowded: Index, query: str, right: str, near: str
) -> None:
    hits = ranked(crowded, query)
    assert hits[0] == right, f"{near} or another unit outranked {right}: {hits}"


@pytest.mark.parametrize("query", NO_RIGHT_UNIT)
def test_a_query_no_unit_is_about_still_returns_matches_with_their_subject(
    crowded: Index, query: str
) -> None:
    hits = crowded.search(query)
    assert hits
    assert all(hit.subject for hit in hits)

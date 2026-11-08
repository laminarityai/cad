"""Recall and near-misses on a ten-source corpus of the kind the agent will ask about."""

import json
from pathlib import Path

import pytest

from cad.knowledge.corpus import load
from cad.knowledge.search import Index

FRONT = (
    "---\ntitle: {title}\nurl: https://example.com/{stem}\nretrieved: 2026-11-07\n"
    "license: own-summary\nsubject: {stem}\naliases: {aliases}\n---\n"
)

SOURCES: dict[str, tuple[str, list[str], str]] = {
    "bambu-pla-basic": (
        "Bambu Lab PLA Basic Technical Data Sheet V3",
        ["Bambu Lab PLA Basic", "Bambu PLA Basic", "PLA Basic"],
        '## Density\nThe table lists "Density 1.26 g/cm³ ISO 1183".\n\n'
        "## Heat deflection temperature\n"
        'The sheet lists "Heat Deflection Temperature (HDT, 0.45 MPa) 57 °C".\n',
    ),
    "bambu-pla-matte": (
        "Bambu Lab PLA Matte Technical Data Sheet V3",
        ["Bambu Lab PLA Matte", "Bambu PLA Matte", "PLA Matte"],
        '## Density\nThe table lists "Density 1.32 g/cm³ ISO 1183".\n',
    ),
    "bambu-petg-hf": (
        "Bambu Lab PETG HF Technical Data Sheet V2",
        ["Bambu Lab PETG HF", "Bambu PETG HF", "PETG HF"],
        '## Density\nPETG HF is a high-flow PETG. The table lists "Density 1.28 g/cm³".\n\n'
        '## Heat deflection temperature\nThe sheet lists "HDT 0.45 MPa 69 °C".\n',
    ),
    "polylite-abs": (
        "PolyLite ABS technical data sheet V5.2 (Polymaker)",
        ["PolyLite ABS", "Polymaker PolyLite ABS"],
        '## Density\nThe table lists "Density 1.04 g/cm3 at 21.5°C".\n\n'
        "## Vicat softening temperature\n"
        'The sheet lists "Vicat softening temperature 103 °C (ASTM D1525)".\n',
    ),
    "polylite-asa": (
        "PolyLite ASA technical data sheet V5.1 (Polymaker)",
        ["PolyLite ASA", "Polymaker PolyLite ASA"],
        '## Weather resistance\nThe sheet says "excellent UV resistance, better than ABS".\n\n'
        '## Density\nThe table lists "Density 1.07 g/cm3".\n',
    ),
    "bambu-pa6-cf": (
        "Bambu Lab PA6-CF Technical Data Sheet",
        ["Bambu Lab PA6-CF", "PA6-CF"],
        '## Drying\nThe nylon absorbs moisture. The sheet says "Drying settings 80 °C, 8 h".\n\n'
        '## Density\nThe table lists "Density 1.25 g/cm³".\n',
    ),
    "ninjaflex-tpu": (
        "NinjaFlex TPU 85A technical specifications (NinjaTek)",
        ["NinjaFlex TPU", "NinjaFlex"],
        '## Shore hardness\nThe sheet lists "Shore Hardness 85A".\n\n'
        '## Density\nThe sheet lists "Specific gravity 1.19".\n',
    ),
    "aluminium-6061": (
        "Aluminum 6061-T6 properties (ASM)",
        ["Aluminum 6061-T6", "6061-T6"],
        '## Density\nThe page lists "Density 2.70 g/cc".\n\n'
        '## Yield strength\nThe page lists "Tensile Yield Strength 276 MPa".\n',
    ),
    "iso-273-clearance": (
        "ISO 273 clearance holes for metric bolts",
        ["ISO 273", "M3", "M4", "M5", "M6"],
        "## Clearance hole sizes\nM3 medium 3.4 mm, M4 medium 4.5 mm, M5 medium 5.5 mm, "
        "M6 medium 6.6 mm.\n",
    ),
    "stainless-316l": (
        "Stainless steel 316L data sheet (AK Steel)",
        ["Stainless steel 316L", "316L stainless steel", "316L"],
        '## Density\nThe sheet lists "Density 0.29 lbs/in3 (8.00 g/cm3)".\n',
    ),
}

HITS = [
    ("Bambu PLA Basic density", "bambu-pla-basic#density"),
    ("PLA Basic density", "bambu-pla-basic#density"),
    ("density of Bambu PLA Basic", "bambu-pla-basic#density"),
    ("PLA Basic density g/cm3", "bambu-pla-basic#density"),
    ("PLA Basic heat deflection temperature", "bambu-pla-basic#heat-deflection-temperature"),
    ("PLA Basic HDT", "bambu-pla-basic#heat-deflection-temperature"),
    ("PLA Matte density", "bambu-pla-matte#density"),
    ("Bambu PLA Matte density", "bambu-pla-matte#density"),
    ("PETG HF density", "bambu-petg-hf#density"),
    ("PETG HF heat deflection temperature", "bambu-petg-hf#heat-deflection-temperature"),
    ("PETG HF HDT", "bambu-petg-hf#heat-deflection-temperature"),
    ("Bambu PETG HF density", "bambu-petg-hf#density"),
    ("PolyLite ABS density", "polylite-abs#density"),
    ("PolyLite ABS Vicat softening temperature", "polylite-abs#vicat-softening-temperature"),
    ("PolyLite ABS vicat temperature", "polylite-abs#vicat-softening-temperature"),
    ("PolyLite ASA UV resistance", "polylite-asa#weather-resistance"),
    ("PolyLite ASA weather resistance", "polylite-asa#weather-resistance"),
    ("PolyLite ASA density", "polylite-asa#density"),
    ("PA6-CF density", "bambu-pa6-cf#density"),
    ("PA6-CF drying", "bambu-pa6-cf#drying"),
    ("PA6 CF density", "bambu-pa6-cf#density"),
    ("NinjaFlex shore hardness", "ninjaflex-tpu#shore-hardness"),
    ("NinjaFlex TPU density", "ninjaflex-tpu#density"),
    ("6061-T6 density", "aluminium-6061#density"),
    ("aluminum 6061-T6 density", "aluminium-6061#density"),
    ("6061-T6 yield strength", "aluminium-6061#yield-strength"),
    ("aluminum 6061-T6 yield strength", "aluminium-6061#yield-strength"),
    ("M5 clearance hole", "iso-273-clearance#clearance-hole-sizes"),
    ("ISO 273 M5 clearance", "iso-273-clearance#clearance-hole-sizes"),
    ("316L density", "stainless-316l#density"),
    ("316L stainless steel density", "stainless-316l#density"),
]
MISSES = [
    ("PA6-CF drying temperature", "bambu-pa6-cf#drying"),
    ("M5 clearance hole size", "iso-273-clearance#clearance-hole-sizes"),
    ("PLA Basic density at 23 °C", "bambu-pla-basic#density"),
    ("PolyLite ABS densities", "polylite-abs#density"),
]
HELD_OUT = [
    ("PLA Basic heat deflection", "bambu-pla-basic#heat-deflection-temperature"),
    ("PolyLite ABS specific gravity", "polylite-abs#density"),
    ("NinjaFlex TPU hardness", "ninjaflex-tpu#shore-hardness"),
    ("aluminium 6061-T6 density", "aluminium-6061#density"),
    ("6061-T6 tensile yield", "aluminium-6061#yield-strength"),
    ("PA6-CF drying time", "bambu-pa6-cf#drying"),
    ("PETG HF HDT temperature", "bambu-petg-hf#heat-deflection-temperature"),
    ("M4 clearance hole diameter", "iso-273-clearance#clearance-hole-sizes"),
    ("316L density g/cm3", "stainless-316l#density"),
    ("PolyLite ASA UV", "polylite-asa#weather-resistance"),
    ("PolyLite ABS vicat", "polylite-abs#vicat-softening-temperature"),
    ("PLA Matte density?", "bambu-pla-matte#density"),
]
NEAR_MISSES = [
    "PLA density",
    "TPU shore hardness",
    "6061 yield strength",
    "ABS density",
    "ASA density",
    "TPU density",
    "6061 density",
    "Polymaker ABS density",
    "PETG density",
    "nylon drying",
    "PA6 density",
    "PLA Silk density",
    "NinjaFlex 95A shore hardness",
    "TPU 95A shore hardness",
    "ABS UV resistance",
    "Bambu density",
    "aluminum 7075-T6 density",
    "304 stainless steel density",
    "steel density",
    "M8 clearance hole",
]


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> Index:
    directory: Path = tmp_path_factory.mktemp("recall")
    for stem, (title, aliases, body) in SOURCES.items():
        front = FRONT.format(title=title, stem=stem, aliases=json.dumps(aliases))
        (directory / f"{stem}.md").write_text(front + body)
    return Index(load(directory))


def answer(index: Index, query: str) -> list[str]:
    return [hit.pointer.id.removeprefix("kb:") for hit in index.search(query)]


def test_every_named_question_finds_its_unit_and_only_its_unit(index: Index) -> None:
    wrong = {q: answer(index, q) for q, expected in HITS if answer(index, q) != [expected]}
    assert wrong == {}


def test_a_known_miss_finds_nothing_rather_than_something_else(index: Index) -> None:
    wrong = {q: answer(index, q) for q, _ in MISSES if answer(index, q) != []}
    assert wrong == {}


def recall(index: Index, asked: list[tuple[str, str]]) -> float:
    return sum(1 for q, expected in asked if answer(index, q) == [expected]) / len(asked)


def test_recall_over_all_the_questions_an_agent_would_ask(index: Index) -> None:
    assert recall(index, [*HITS, *MISSES]) >= 0.85


def test_held_out_paraphrases_never_return_a_wrong_unit(index: Index) -> None:
    wrong = {q: answer(index, q) for q, e in HELD_OUT if answer(index, q) not in ([e], [])}
    assert wrong == {}


def test_held_out_paraphrases_are_not_all_misses(index: Index) -> None:
    assert recall(index, HELD_OUT) >= 0.5


@pytest.mark.parametrize("query", NEAR_MISSES)
def test_a_near_miss_finds_nothing(index: Index, query: str) -> None:
    assert answer(index, query) == []

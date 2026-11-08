from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from cad.knowledge.search import Hit

if TYPE_CHECKING:
    from conftest import MakeIndex


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


def test_m5_returns_nothing_when_only_m6_is_present(make_index: MakeIndex) -> None:
    index = make_index({"metric": "## Clearance holes\nM6 clearance hole is 6.6 mm.\n"})
    assert index.search("M5 clearance hole") == ()
    assert ids(index.search("M6 clearance hole")) == ["kb:metric#clearance-holes"]


def test_m5_does_not_match_m5x0_8(make_index: MakeIndex) -> None:
    index = make_index({"metric": "## Pitch\nM5x0.8 is the coarse thread pitch.\n"})
    assert index.search("M5 thread pitch") == ()
    assert ids(index.search("M5x0.8 thread pitch")) == ["kb:metric#pitch"]


def test_a_decimal_is_one_token(make_index: MakeIndex) -> None:
    index = make_index({"drill": "## Sizes\nThe drill size 5.5 mm suits a tap.\n"})
    assert index.search("drill size 5 mm") == ()
    assert index.search("drill size 55 mm") == ()
    assert ids(index.search("drill size 5.5 mm")) == ["kb:drill#sizes"]


def test_petg_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index({"pla": "## Density\nPLA density from the data sheet.\n"})
    assert index.search("PETG density") == ()
    assert ids(index.search("PLA density")) == ["kb:pla#density"]


def test_pla_never_returns_pla_plus(make_index: MakeIndex) -> None:
    index = make_index({"plus": "## Density\nPLA+ density from the data sheet.\n"})
    assert index.search("PLA density") == ()
    assert ids(index.search("PLA+ density")) == ["kb:plus#density"]


def test_pla_plus_never_returns_pla(make_index: MakeIndex) -> None:
    index = make_index({"plain": "## Density\nPLA density from the data sheet.\n"})
    assert index.search("PLA+ density") == ()


def test_petg_basic_hf_and_cf_stay_apart(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "petg-basic": "## Density\nBambu PETG Basic density.\n",
            "petg-hf": "## Density\nBambu PETG HF density.\n",
            "petg-cf": "## Density\nBambu PETG CF density.\n",
        }
    )
    assert ids(index.search("Bambu PETG HF density")) == ["kb:petg-hf#density"]
    assert ids(index.search("Bambu PETG CF density")) == ["kb:petg-cf#density"]
    assert ids(index.search("Bambu PETG Basic density")) == ["kb:petg-basic#density"]
    assert index.search("Bambu PETG GF density") == ()


def test_lowercase_queries_do_not_drift_to_a_sibling(make_index: MakeIndex) -> None:
    index = make_index(
        {
            "pla": "## Density\nPLA density from the data sheet.\n",
            "petg-hf": "## Density\nBambu PETG HF density.\n",
        }
    )
    assert index.search("pla+ density") == ()
    assert index.search("petg basic density") == ()
    assert index.search("petg cf density") == ()
    assert ids(index.search("petg hf density")) == ["kb:petg-hf#density"]

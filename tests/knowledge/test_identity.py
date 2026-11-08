"""Identity through the real loader: a branded file answers only to names that carry its brand."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import pytest

from cad.knowledge.corpus import InvalidCorpus
from cad.knowledge.search import Hit

if TYPE_CHECKING:
    from conftest import MakeIndex

DENSITY = '## Density\nThe sheet lists "Density 1.00 g/cm3".\n'

GENERIC_NAMES = [
    *[("Dow", a) for a in ("HDPE", "LDPE", "PE")],
    *[("DuPont", a) for a in ("POM", "acetal", "Delrin")],
    *[("Arkema", a) for a in ("PMMA", "acrylic")],
    ("Geon", "PVC"),
    *[("Solvay", a) for a in ("PPS", "PSU")],
    *[("Bambu Lab", a) for a in ("CF", "GF", "PLA-CF", "PA6-CF", "PETG CF", "PLA Matte")],
    *[("Bambu Lab", a) for a in ("PLA Silk", "PLA Basic", "PETG HF", "polycarbonate PC")],
    *[("Bambu Lab", a) for a in ("TPU 95A", "ASA Aero", "the PLA", "PLA ®", "PLAs")],
    *[("Bambu Lab", a) for a in ("PLA filament", "PLA material", "3D printing PLA")],
    *[("Bambu Lab", a) for a in ("a PLA", "PA 6", "PA 12", "nylon 6", "PLA™", "6061 aluminum")],
    ("Polymaker", "carbon fiber PLA"),
    ("British Steel", "mild steel"),
    *[("McMaster", a) for a in ("1018", "4140", "bronze", "zinc", "rubber", "neoprene")],
    *[("AK Steel", a) for a in ("17-4", "17-4 PH", "stainless", "SS", "SS304", "304L", "316L")],
    *[("AK Steel", a) for a in ("stainless 316", "stainless steel 316L")],
    *[("Alcoa", a) for a in ("6063", "6082", "Al", "aluminum alloy", "6061-T6", "Al 6061")],
    *[("ATI", a) for a in ("Ti-6Al-4V", "Ti64", "grade 5 titanium")],
    ("colorFabb", "wood"),
    *[("Elegoo", a) for a in ("resin", "standard resin")],
    *[("eSUN", a) for a in ("filament", "PLA Pro", "ABS+", "PETG+")],
    *[("Polymaker", a) for a in ("nylon 12", "PA 12")],
    *[("Chemours", a) for a in ("PTFE", "Teflon")],
]


def ids(hits: Sequence[Hit]) -> list[str]:
    return [hit.pointer.id for hit in hits]


@pytest.mark.parametrize(("maker", "alias"), GENERIC_NAMES)
def test_a_generic_name_on_a_branded_file_is_refused(
    make_index: MakeIndex, maker: str, alias: str
) -> None:
    with pytest.raises(InvalidCorpus, match="maker or line"):
        make_index({"branded": DENSITY}, {"branded": [alias]}, maker=maker)


def test_a_branded_file_without_a_maker_is_refused(make_index: MakeIndex) -> None:
    with pytest.raises(InvalidCorpus, match="maker"):
        make_index({"branded": DENSITY}, {"branded": ["PolyTerra PLA"]})


def test_a_family_file_and_a_branded_file_answer_their_own_names(make_index: MakeIndex) -> None:
    make_index(
        {"pla": '## Density\nThe handbook lists "1.24 g/cm3".\n'}, {"pla": ["PLA"]}, family=True
    )
    index = make_index(
        {"polyterra-pla": DENSITY},
        {"polyterra-pla": ["PolyTerra PLA", "Polymaker PolyTerra PLA"]},
        maker="Polymaker",
        line="PolyTerra",
    )
    assert ids(index.search("PLA density")) == ["kb:pla#density"]
    assert ids(index.search("the PLA density")) == ["kb:pla#density"]
    assert ids(index.search("PolyTerra PLA density")) == ["kb:polyterra-pla#density"]
    assert ids(index.search("Polymaker PolyTerra PLA density")) == ["kb:polyterra-pla#density"]
    for query in ("PolyTerra density", "PLA PolyTerra density", "PLA density PolyTerra"):
        assert index.search(query) == (), query


def test_a_variant_named_only_in_a_quote_is_not_the_plain_grade(make_index: MakeIndex) -> None:
    index = make_index(
        {"polylite-petg": '## Density\n"Density 1.25 g/cm3. For stiffness choose the CF grade".\n'},
        {"polylite-petg": ["PolyLite PETG"]},
        maker="Polymaker",
        line="PolyLite",
    )
    assert index.search("PolyLite PETG CF density") == ()
    assert ids(index.search("PolyLite PETG density")) == ["kb:polylite-petg#density"]


def test_a_hardness_named_only_in_a_quote_is_not_the_one_the_unit_has(
    make_index: MakeIndex,
) -> None:
    index = make_index(
        {"ninjaflex": '## Shore hardness\n"Shore Hardness 85A; see Cheetah for 95A".\n'},
        {"ninjaflex": ["NinjaFlex"]},
        maker="NinjaTek",
        line="NinjaFlex",
    )
    assert index.search("NinjaFlex 95A shore hardness") == ()
    assert ids(index.search("NinjaFlex shore hardness")) == ["kb:ninjaflex#shore-hardness"]

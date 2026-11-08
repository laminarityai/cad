"""Words that name a kind of material, never one maker's product.

The maker rule in `cad.knowledge.corpus` reads this list and nothing else does. A branded file's
alias must carry a word of its maker or product line, and a word on this list does not count:
"British Steel" lends an alias only "british", so "mild steel" is refused. An alias of only the
maker's name and words on this list ("Bambu PLA") names a group and is refused too. A word
missing from the list never lets an alias without a brand word through. It does let "Bambu CPE"
through while CPE is unlisted, so review checks that such a name is one product. The words are
case-folded and compared case-folded, so "pa6" is a family word although a search keeps the case
of a word with a digit.
"""

from typing import Final

from cad.knowledge.text import tokens

FAMILY_NAMES: Final = (
    *("PLA", "PLA+", "PETG", "PET", "ABS", "ASA", "TPU", "TPE", "HIPS", "PVA", "PP", "PC", "PEEK"),
    *("PEI", "PA", "PA6", "PA12", "PA66", "nylon", "polycarbonate", "polypropylene"),
    *("PE", "HDPE", "LDPE", "PVC", "POM", "acetal", "acrylic", "PMMA", "PTFE", "rubber", "resin"),
    *("steel", "stainless", "aluminum", "aluminium", "titanium", "brass", "bronze", "copper"),
    *("zinc", "iron", "metal", "metals", "alloy", "alloys", "plastic", "plastics", "polymer"),
    *("polymers", "material", "materials", "filament", "filaments", "carbon", "fiber", "fibre"),
    *("glass", "wood", "3D", "print", "printing"),
    *("6061", "7075", "2024", "5052", "304", "316"),
)
FAMILY_WORDS: Final = frozenset(word.casefold() for name in FAMILY_NAMES for word in tokens(name))

"""Names of whole families of material. A branded product may not claim one as an alias.

"PLA" means every PLA there is. A data sheet for one brand's PLA is not an answer to "PLA
density", so the loader refuses these names as aliases unless the file declares `family: true`,
meaning the source really is about the whole family. Names are written as a person would type
them; the loader reads them through `cad.knowledge.text.tokens`.
"""

from typing import Final

from cad.knowledge.text import tokens

FAMILY_NAMES: Final = (
    *("PLA", "PLA+", "PETG", "PET", "ABS", "ASA", "TPU", "TPE", "HIPS", "PVA", "PP", "PC", "PEEK"),
    *("PEI", "PA", "PA6", "PA12", "PA66", "nylon", "polycarbonate", "polypropylene"),
    *("steel", "stainless steel", "aluminum", "aluminium", "titanium", "brass", "copper"),
    *("6061", "7075", "2024", "5052", "304", "316"),
)
FAMILIES: Final = frozenset(tokens(name) for name in FAMILY_NAMES)

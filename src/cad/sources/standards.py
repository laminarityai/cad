"""The density test standards the reader knows, as exact spellings.

A quote often puts the value right after the standard, as in "ISO 1183 1.24 g/cm3". From its
shape alone, "DIN 1 2400" could be DIN 1 then 2400 or DIN 12 then 400, so the reader cannot tell
where a standard ends. A spelling listed here ends exactly where it ends, so a number with a
decimal mark after it reads. A whole number after it, past any separators, is refused, because
"ISO 1183: 2019" could name the 2019 edition. Add a spelling only as a datasheet writes it, with
its spaces, part and year.
"""

from typing import Final

STANDARDS: Final[dict[str, tuple[str, ...]]] = {
    "ISO 1183": ("ISO 1183", "ISO1183", "ISO 1183:2019"),
    "ISO 1183-1": (
        "ISO 1183-1",
        "ISO1183-1",
        "ISO 1183-1:2004",
        "ISO 1183-1:2012",
        "ISO 1183-1:2019",
    ),
    "ISO 1183-2": ("ISO 1183-2", "ISO1183-2", "ISO 1183-2:2004", "ISO 1183-2:2019"),
    "ISO 1183-3": ("ISO 1183-3", "ISO1183-3", "ISO 1183-3:1999"),
    "EN ISO 1183": ("EN ISO 1183",),
    "EN ISO 1183-1": ("EN ISO 1183-1", "EN ISO 1183-1:2019"),
    "DIN EN ISO 1183": ("DIN EN ISO 1183",),
    "DIN EN ISO 1183-1": ("DIN EN ISO 1183-1", "DIN EN ISO 1183-1:2019"),
    "DIN EN ISO 1183-2": ("DIN EN ISO 1183-2", "DIN EN ISO 1183-2:2019"),
    "DIN 53479": ("DIN 53479",),
    "ASTM D792": (
        "ASTM D792",
        "ASTM D 792",
        "ASTM D792-13",
        "ASTM D 792-13",
        "ASTM D792-20",
        "ASTM D 792-20",
    ),
    "ASTM D1505": ("ASTM D1505", "ASTM D 1505", "ASTM D1505-18", "ASTM D 1505-18"),
    "GB/T 1033": ("GB/T 1033", "GB/T1033"),
    "GB/T 1033.1": ("GB/T 1033.1", "GB/T1033.1", "GB/T 1033.1-2008"),
    "JIS K 7112": ("JIS K 7112", "JIS K7112", "JIS K 7112:1999"),
    "JIS K 7112-1": ("JIS K 7112-1", "JIS K 7112-1:2023"),
}

"""A section's names: its heading and the keys it declares, read the way a query is read.

`<!-- keys: HDT, heat deflection -->` under a heading declares exact other names, separated by
commas. Each name, the heading included, is cut into words (`cad.knowledge.text`), and the runs
that are one of the subject's aliases and every stopword are taken out. A query chooses the unit
whose name equals its own leftover words.
"""

import re
from collections.abc import Iterable
from typing import Final

from cad.knowledge.text import STOPWORDS, tokens

KEYS: Final = re.compile(r"<!--\s*keys:\s*(?P<keys>[^>]*?)\s*-->")
KEYS_LIKE: Final = re.compile(r"<!--\s*keys", re.IGNORECASE)

type Alias = tuple[str, ...]
type Name = frozenset[str]


def section_words(words: tuple[str, ...], aliases: Iterable[Alias]) -> Name:
    """The words left once every run that is one of `aliases` and every stopword is taken out."""
    named = {
        i
        for alias in aliases
        for start in range(len(words) - len(alias) + 1)
        if words[start : start + len(alias)] == alias
        for i in range(start, start + len(alias))
    }
    return frozenset(w for i, w in enumerate(words) if i not in named and w not in STOPWORDS)


def section_names(
    aliases: frozenset[Alias], section: str, text: str, visible: str
) -> tuple[frozenset[Name], str] | str:
    """The section's names and its text without the keys comment, or the problem.

    `visible` is `text` with its code blocks blanked, offsets kept: a keys comment inside a code
    block is text, and a comment that starts like one but is malformed is refused.
    """
    found = list(KEYS.finditer(visible))
    if len(KEYS_LIKE.findall(visible)) != len(found):
        return f"section {section!r}: a keys comment must read `<!-- keys: name, other name -->`"
    if len(found) > 1:
        return f"section {section!r}: more than one keys comment"
    names = {section_words(tokens(section), aliases)}
    if found:
        text = text[: found[0].start()] + text[found[0].end() :]
        for key in found[0]["keys"].split(","):
            words = tokens(key)
            if not any(w[0].isalnum() for w in words):
                return f"section {section!r}: empty key or a key with no letter or digit"
            if all(w in STOPWORDS for w in words):
                return f"section {section!r}: key {key.strip()!r} is only stopwords"
            name = section_words(words, aliases)
            if not name:
                return f"section {section!r}: key {key.strip()!r} is only the subject's name"
            names.add(name)
    names.discard(frozenset[str]())
    if not names:
        return (
            f"section {section!r} can never be found: its heading is only the subject's name "
            "and stopwords; add a word or a keys comment"
        )
    return frozenset(names), text

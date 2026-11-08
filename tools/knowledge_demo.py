import sys
import textwrap

from cad.knowledge.corpus import CORPUS_PATH, load
from cad.knowledge.search import Index

QUERIES = (
    "fresh water density",
    "water density at 4 degrees",
    "pure water at 4 degrees",
    "mineral water density",
    "PLA density",
    "Polymaker PLA density",
    "PolyTerra PLA density",
    "PLA+ density",
    "PolyTerra PLA+ density",
    "!PLA density",
    "PETG density",
    "PA6-CF density",
    "HDPE density",
    "PLA Matte density",
    "pla+ toughness",
    "PolyTerra PLA plus density",
    "PLA toughness",
    "PolyTerra density",
    "PolyTerra PLA\u2795 density",
    "ISO1183 density",
    "M5 clearance hole",
    "water viscosity",
    "water",
)


WIDTH = 92


def ascii_only(text: str) -> str:
    return "".join(c if c.isascii() else f"\\u{ord(c):04x}" for c in text)


def main() -> None:
    corpus = load(CORPUS_PATH)
    index = Index(corpus)
    print(f"corpus {corpus.version[:12]}: {len(corpus.units)} units")
    for query in sys.argv[1:] or QUERIES:
        hits = index.search(query)
        print(f"\n> {ascii_only(query)}")
        if not hits:
            print("  no confident hit")
        for hit in hits:
            pointer = hit.pointer
            page = f", page {pointer.page}" if pointer.page else ""
            print(f"  {pointer.id}  (section {pointer.section!r}{page})")
            for line in textwrap.wrap(ascii_only(pointer.title), WIDTH):
                print(f"    {line}")
            print(f"    {pointer.url}")
            for line in textwrap.wrap(ascii_only(hit.text), WIDTH):
                print(f"    | {line}")


if __name__ == "__main__":
    main()

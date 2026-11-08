import sys

from cad.knowledge.corpus import CORPUS_PATH, load
from cad.knowledge.search import Index

QUERIES = (
    "fresh water density",
    "water density at 4 degrees",
    "PLA density",
    "PLA+ density",
    "PETG density",
    "pla+ toughness",
    "PLA plus density",
    "PLA toughness",
    "PolyTerra density",
    "PLA\u2795 density",
    "ISO1183 density",
    "M5 clearance hole",
    "water viscosity",
    "water",
)


def main() -> None:
    corpus = load(CORPUS_PATH)
    index = Index(corpus)
    print(f"corpus {corpus.version[:12]}: {len(corpus.units)} units")
    for query in sys.argv[1:] or QUERIES:
        hits = index.search(query)
        print(f"\n> {query}")
        if not hits:
            print("  no confident hit")
        for hit in hits:
            pointer = hit.pointer
            page = f", page {pointer.page}" if pointer.page else ""
            print(f"  {pointer.id}  ({pointer.title}, section {pointer.section!r}{page})")
            print(f"    {pointer.url}")


if __name__ == "__main__":
    main()

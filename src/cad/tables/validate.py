import sys

from cad.tables.datasheet_text import quote_problems
from cad.tables.materials import InvalidTable, load_materials


def main() -> int:
    try:
        table = load_materials()
    except InvalidTable as error:
        for problem in error.problems:
            print(problem)
        return 1
    problems = quote_problems(table)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"materials table {table.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

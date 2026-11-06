import logging
import sys

from cad.server.app import build_server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    build_server().run("stdio")


if __name__ == "__main__":
    main()

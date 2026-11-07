import logging
import sys
from contextlib import suppress

from cad.sandbox import container
from cad.sandbox.outcome import SandboxUnavailable
from cad.server.app import build_server


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    with suppress(SandboxUnavailable):
        container.remove_orphans()
    build_server().run("stdio")


if __name__ == "__main__":
    main()

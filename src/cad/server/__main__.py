import argparse
import logging
import sys
from contextlib import suppress

from cad.confirmations.waiting import program_opener
from cad.sandbox import container
from cad.sandbox.outcome import SandboxUnavailable
from cad.server.app import build_server
from cad.server.stopping import checks_end_with_the_server


def main() -> None:
    parser = argparse.ArgumentParser(prog="cad-server", description="The cad MCP server, on stdio.")
    parser.add_argument(
        "--opener",
        default="open",
        metavar="PROGRAM",
        help="program the server runs with each sign-in link to the page (default: open)",
    )
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    with suppress(SandboxUnavailable):
        container.remove_orphans()
    with checks_end_with_the_server():
        build_server(opener=program_opener(args.opener)).run("stdio")


if __name__ == "__main__":
    main()

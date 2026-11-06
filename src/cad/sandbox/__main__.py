import argparse
import sys
from collections.abc import Sequence

from cad.sandbox.image import build_image
from cad.sandbox.outcome import SandboxUnavailable


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cad-sandbox", description="Manage the sandbox image.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build-image", help="build the sandbox image unless the current one exists")
    parser.parse_args(argv)
    try:
        print(build_image())
    except SandboxUnavailable as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

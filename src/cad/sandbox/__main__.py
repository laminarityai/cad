import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from cad.sandbox.host import run_checks
from cad.sandbox.image import build_images
from cad.sandbox.outcome import SandboxUnavailable
from cad.variants.entry import VARIANTS_ROOT, StaleVariant, VariantRefused


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cad-sandbox", description="Manage the sandbox images and check stored variants."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "build-image", help="build the build and analysis images unless the current ones exist"
    )
    checks = commands.add_parser(
        "run-checks",
        help="run the checks on a built variant and print the result",
    )
    checks.add_argument("variant_id", help="the id build_variant returned")
    checks.add_argument(
        "material_key", help="a key of tables/materials.yaml, such as prusament-pla"
    )
    checks.add_argument("--root", type=Path, default=VARIANTS_ROOT, help="the variant store")
    args = parser.parse_args(argv)
    try:
        if args.command == "run-checks":
            run = run_checks(str(args.variant_id), str(args.material_key), Path(str(args.root)))
            print(run.model_dump_json(indent=2))
        else:
            print(build_images())
    except VariantRefused as error:
        kind = StaleVariant if isinstance(error, StaleVariant) else type(error)
        print(f"{kind.__name__}: {error}")
        return 1
    except SandboxUnavailable as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

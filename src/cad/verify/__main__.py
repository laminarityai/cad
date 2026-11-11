import argparse
import sys
from collections.abc import Sequence

from cad.verify.runner import run_steps
from cad.verify.steps import STEPS, Step


def select_steps(only: Sequence[str] | None) -> Sequence[Step]:
    if only is None:
        return STEPS
    return [step for step in STEPS if step.name in only]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify", description="Run every verify step in order.")
    parser.add_argument(
        "--only",
        action="append",
        choices=[step.name for step in STEPS],
        help="run this step; repeat it to run several, in verify's order",
    )
    args = parser.parse_args(argv)
    return run_steps(select_steps(args.only))


if __name__ == "__main__":
    sys.exit(main())

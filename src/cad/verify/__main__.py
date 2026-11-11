import argparse
import sys
from collections.abc import Sequence

from cad.verify.runner import run_steps
from cad.verify.steps import STEPS, Step


def select_steps(only: Sequence[str] | None, *, every: bool = False) -> Sequence[Step]:
    if only is not None:
        return [step for step in STEPS if step.name in only]
    if every:
        return STEPS
    return [step for step in STEPS if not step.slow]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify",
        description="Run the fast verify steps side by side. CI runs every step on each PR.",
    )
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--all", action="store_true", help="run every step, the slow ones too")
    choice.add_argument(
        "--only",
        action="append",
        choices=[step.name for step in STEPS],
        help="run this step; repeat it to run several, in verify's order",
    )
    args = parser.parse_args(argv)
    steps = select_steps(args.only, every=args.all)
    code = run_steps(steps)
    if code == 0 and len(steps) < len(STEPS) and args.only is None:
        print("The slow steps run in CI: push and read `gh pr checks`.")
    return code


if __name__ == "__main__":
    sys.exit(main())

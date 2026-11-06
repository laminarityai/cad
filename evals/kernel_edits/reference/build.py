"""Write the reference STEP files the grader reads.

reference/<brief>.step is the reference for each brief. reference/start/<start>.step is
the build123d starting model's own output, exported from start/build123d/<start>.py.
Run in the build123d env: uv run --project evals/kernel_edits/envs/build123d python
evals/kernel_edits/reference/build.py
"""

import sys
from pathlib import Path

from build123d import Part

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from export import result_of, write_step  # noqa: E402
from reference import assemblies, edits  # noqa: E402

REFERENCES = {**edits.REFERENCES, **assemblies.REFERENCES}
STARTS = {**edits.STARTS, **assemblies.STARTS}


def write_parts(found: list[Part], path: Path) -> None:
    write_step([p.wrapped for p in found if p.wrapped is not None], path)


def main() -> int:
    (ROOT / "reference" / "start").mkdir(exist_ok=True)
    for start_id in STARTS:
        script = ROOT / "start" / "build123d" / f"{start_id}.py"
        write_step(result_of(script), ROOT / "reference" / "start" / f"{start_id}.step")
    for brief_id, build in REFERENCES.items():
        write_parts(build(), ROOT / "reference" / f"{brief_id}.step")
    print(f"wrote {len(STARTS)} starting models and {len(REFERENCES)} references")
    return 0


if __name__ == "__main__":
    sys.exit(main())

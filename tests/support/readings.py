"""A variant stored as the server stores it, with its quick results, so the server's own
`scorecard` read finds it with no build and no sandbox."""

from pathlib import Path

from cad.checks.container.check import Quick
from cad.checks.job_store import write
from cad.checks.jobs import JobResult, JobSpec
from cad.checks.report import QUICK, build_request
from cad.checks.result import StepStored
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.variants import entry
from tests.support.cards import BREP, KEY, STEP, STEP_SHA, genuine_result, table


def scored_variant(variants: Path, code: str = "x = 1\n") -> str:
    tag = image_tag(BUILD)
    vid = entry.variant_id(code, tag)
    entry.save(variants, vid, code, Build(outcome=Built(), output=""), BREP)
    (variants / vid / entry.STEP).write_bytes(STEP)
    held = entry.open_entry(variants, vid, tag)
    quick = JobSpec(variants, vid, held.brep_sha256, QUICK, Quick(), build_request(KEY, table()))
    results = tuple(genuine_result(spec) for spec in QUICK)
    write(
        quick,
        JobResult(
            check_image_digest="sha256:" + "i" * 64,
            step=StepStored(sha256=STEP_SHA),
            results=results,
        ),
    )
    return vid

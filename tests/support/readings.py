"""A variant stored as the server stores it, with its quick results, so the server's own
`scorecard` read finds it with no build and no sandbox."""

from pathlib import Path

from readings import read_after
from trace_store import trace_cards

from cad.briefs import store as briefs
from cad.checks.container.check import Quick
from cad.checks.job_store import write
from cad.checks.jobs import JobResult, JobSpec
from cad.checks.report import QUICK, build_request
from cad.checks.result import StepStored
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.scorecard.model import Scorecard
from cad.variants import entry
from tests.support.cards import BREP, BRIEF_TEXT, KEY, STEP, STEP_SHA, genuine_result, table


def a_session(tmp_path: Path) -> tuple[Path, Path, Roots, str]:
    """A home with an empty variant store and one brief: the home, the variant store, the brief
    and project roots, and the brief id."""
    home = tmp_path / "home"
    variants = home / ".cad" / "variants"
    variants.mkdir(parents=True)
    roots = Roots(home / ".cad" / "briefs", home / ".cad" / "projects")
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    return home, variants, roots, brief_id


def reading_of(home: Path, card: Scorecard) -> str:
    """The server's reading of the variant, material and brief that `card` names."""
    stores = home / ".cad"
    roots = Roots(stores / "briefs", stores / "projects")
    shown = trace_cards([card.model_dump_json()], stores / "variants", roots)
    [reading] = read_after(stores, shown)
    assert isinstance(reading, str), reading
    return reading


def scored_variant(variants: Path, code: str = "x = 1\n", version: str | None = None) -> str:
    """`version`, when given, is the check version each stored result names."""
    tag = image_tag(BUILD)
    vid = entry.variant_id(code, tag)
    entry.save(variants, vid, code, Build(outcome=Built(), output=""), BREP)
    (variants / vid / entry.STEP).write_bytes(STEP)
    held = entry.open_entry(variants, vid, tag)
    quick = JobSpec(variants, vid, held.brep_sha256, QUICK, Quick(), build_request(KEY, table()))
    results = tuple(
        genuine_result(spec).model_copy(update={"version": version or spec.version})
        for spec in QUICK
    )
    write(
        quick,
        JobResult(
            check_image_digest="sha256:" + "i" * 64,
            step=StepStored(sha256=STEP_SHA),
            results=results,
        ),
    )
    return vid

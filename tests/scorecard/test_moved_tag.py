import hashlib
import itertools
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest

from cad.checks.result import StepStored
from cad.sandbox import container, image
from cad.sandbox.container import Job, Ran
from cad.scorecard import score
from cad.scorecard.model import Scorecard
from cad.variants import entry

PLATE = (Path(__file__).parents[1] / "sandbox/parts/plate.py").read_text()
OTHER = "sha256:" + "f" * 64

type Build = Callable[[str], str]


@pytest.fixture
def check_images(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real = image.current_image(image.image_tag(image.ANALYSIS))
    real_run = container.run
    started: list[str] = []

    def run(job: Job) -> Ran:
        if job.kind == "check":
            started.append(job.image_id)
        return real_run(replace(job, image_id=real) if job.image_id == OTHER else job)

    monkeypatch.setattr(container, "run", run)
    return started


def lookups_see_other(monkeypatch: pytest.MonkeyPatch, moved: tuple[bool, ...]) -> None:
    real_find = image.find_image
    each_lookup = itertools.chain(moved, itertools.repeat(moved[-1]))

    def find(tag: str) -> str | None:
        return OTHER if next(each_lookup) else real_find(tag)

    monkeypatch.setattr(image, "find_image", find)


@pytest.mark.parametrize(
    "moved", [(False, True, False), (False, False, True)], ids=["away-and-back", "away-during-run"]
)
def test_a_moving_tag_gives_a_stored_scorecard_naming_the_image_the_checks_ran_in(
    moved: tuple[bool, ...],
    built: Build,
    store: Path,
    check_images: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variant_id = built(PLATE + f"# moved tag {moved}\n")
    lookups_see_other(monkeypatch, moved)
    card = score.score_variant(variant_id, "prusament-pla", store)
    assert check_images == [card.check_image_digest]
    directory = store / variant_id
    assert Scorecard.model_validate_json((directory / score.SCORECARD).read_text()) == card
    step = (directory / entry.STEP).read_bytes()
    assert card.step == StepStored(sha256=hashlib.sha256(step).hexdigest())

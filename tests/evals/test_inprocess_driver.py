import json
from functools import partial
from pathlib import Path
from typing import Any, Final

import pytest
import run
from autoresult import Expect, judge
from brief_set import BriefInput, load_set
from inprocess import SCRIPTED, MissingKey, require_key, run_brief

from cad.auto.model import Bounds
from cad.chat.key_file import load_key

KEY: Final = "ANTHROPIC_API_KEY"
HEAVY_CUBE: Final = (
    "A weight for holding down papers that has to fit in a 25 mm cube, made of PETG, at least 80 g."
)
PLATE: Final = "A flat tag for a key ring, aluminium, under 30 g."


def grader(*requirements: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"requirements": list(requirements), **extra}


def mass(kind: str, grams: float, quote: str) -> dict[str, Any]:
    return {"quote": quote, "kind": kind, "target": grams, "unit": "g"}


CUBE_GRADER: Final = grader(
    {"quote": "fit in a 25 mm cube", "kind": "envelope", "target": [25, 25, 25], "unit": "mm"},
    {"quote": "PETG", "kind": "made_of", "material": "prusament-petg"},
    mass("min_mass", 80, "at least 80 g"),
    expect={"stop": "conflict"},
)
TAG_GRADER: Final = grader(
    mass("max_mass", 30, "under 30 g"), material="kaiser-6061-t6", expect={"stop": "agent_asked"}
)


@pytest.fixture(autouse=True)
def quick_person(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAD_HUMAN_DELAY", "0")


def test_a_cube_that_cannot_weigh_what_it_must_stops_with_its_bounds_before_any_build(
    tmp_path: Path,
) -> None:
    brief = BriefInput("cube", "tests", HEAVY_CUBE, CUBE_GRADER)
    result = run_brief(brief, tmp_path, SCRIPTED, None, 60)
    assert result.status == "stopped"
    assert result.stop == "conflict"
    [bounds] = result.bounds
    assert bounds.quantity == "mass"
    assert "min_mass 80 g >" in bounds.statement
    assert result.mode == "design"
    assert (result.revisions, result.variants, result.containers) == (0, 0, 0)
    assert result.pages == 1
    assert result.passed
    events = json.loads((tmp_path / "cube" / "events.json").read_text())
    called = [one["name"] for one in events if one.get("kind") == "tool_call"]
    assert called == ["create_brief", "propose_requirements", "ask_to_confirm", "auto_start"]
    assert events[-1]["kind"] == "turn_ended"


def test_a_brief_that_agrees_with_itself_is_not_stopped_as_a_conflict(tmp_path: Path) -> None:
    brief = BriefInput("tag", "tests", PLATE, TAG_GRADER)
    result = run_brief(brief, tmp_path, SCRIPTED, None, 60)
    assert (result.stop, result.bounds, result.mode) == ("agent_asked", (), "design")
    assert result.passed


def test_the_cube_run_fails_when_the_brief_expects_a_stop_it_did_not_get(tmp_path: Path) -> None:
    brief = BriefInput("tag", "tests", PLATE, {**TAG_GRADER, "expect": {"stop": "conflict"}})
    result = run_brief(brief, tmp_path, SCRIPTED, None, 60)
    assert not result.passed
    assert result.problems == ("expected the stop conflict, got agent_asked",)


def test_a_requirement_the_server_refuses_is_a_tool_error_in_the_result(tmp_path: Path) -> None:
    bad = grader({"quote": "not in the brief", "kind": "closed_solid"}, expect={"stop": "x"})
    result = run_brief(BriefInput("bad", "tests", PLATE, bad), tmp_path, SCRIPTED, None, 60)
    assert result.tool_errors >= 1
    assert not result.passed


def test_the_agents_note_is_judged_only_for_a_live_model() -> None:
    expect = Expect.of({"expect": {"stop": "agent_asked", "names": [["stiff"], ["mass"]]}})
    assert judge(expect, False, "agent_asked", "fixed text", 0, ()) == ()
    assert judge(expect, True, "agent_asked", "stiffness and the mass", 0, ()) == ()
    [missing] = judge(expect, True, "agent_asked", "stiffness only", 0, ())
    assert missing == "the stop's report names none of mass"


def test_the_revision_limit_and_the_bounds_of_a_conflict_are_judged() -> None:
    limited = Expect.of({"expect": {"stop": "agent_asked", "within_revisions": 6}})
    assert judge(limited, True, "agent_asked", "", 7, ()) == ("7 revisions, more than 6",)
    conflict = Expect.of({"expect": {"stop": "conflict"}})
    assert judge(conflict, True, "conflict", "", 0, ()) == ("a conflict stop carried no Bounds",)
    held = (Bounds(quantity="mass", statement="a > b", requirements=("r1",)),)
    assert judge(conflict, True, "conflict", "", 0, held) == ()


def test_a_live_model_without_its_key_is_refused_before_any_server_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(KEY, raising=False)
    monkeypatch.setattr(run, "load_key", partial(load_key, path=tmp_path / "anthropic.env"))
    (tmp_path / "briefs").mkdir()
    code = run.main(
        [
            "--driver",
            "inprocess",
            "--model",
            "claude-haiku-4-5-20251001",
            "--briefs",
            str(tmp_path / "briefs"),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 1
    assert KEY in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
    require_key(SCRIPTED, {})
    with pytest.raises(MissingKey):
        require_key("claude-haiku-4-5-20251001", {KEY: " "})


def test_the_driver_runs_the_set_through_run_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    briefs = tmp_path / "briefs"
    briefs.mkdir()
    (briefs / "cube.yaml").write_text(
        json.dumps({"id": "cube", "domain": "tests", "brief": HEAVY_CUBE, "grader": CUBE_GRADER})
    )
    assert [one.grader for one in load_set(briefs)[0]] == [CUBE_GRADER]
    code = run.main(
        ["--driver", "inprocess", "--briefs", str(briefs), "--out", str(tmp_path / "out")]
    )
    assert code == 0
    assert "1 of 1 briefs passed" in capsys.readouterr().out
    rows = json.loads((tmp_path / "out" / "auto-summary.json").read_text())
    assert [(one["id"], one["stop"]) for one in rows] == [("cube", "conflict")]

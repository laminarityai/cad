import json
import os
from pathlib import Path

import pytest
import run
from brief_set import load_set, prompt_for
from cards import (
    BREP,
    BRIEF_TEXT,
    STEP,
    VARIANT_ID,
    confirm_on_page,
    drafts,
    genuine_card,
    judged_card,
    put,
)
from friction import minutes_to_first_scorecard, read_pages
from outcome import BriefResult, Friction, Share, Trace, is_finished
from session import SessionFacts, SessionRun, failure_note
from summary import markdown, summarize
from tracefacts import NO_CARD, trace_session

from cad.briefs import store as briefs
from cad.projects.model import new_project_id
from cad.records.roots import Roots
from cad.sandbox.outcome import Build, Built
from cad.scorecard.score import SCORECARD
from cad.variants import entry

LIGHT = ({"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}}, "under 150 g")
FRIENDLY = ({"kind": "unchecked", "statement": "looks friendly"}, "looks friendly")


def write_brief(directory: Path, name: str, text: str) -> None:
    (directory / f"{name}.yaml").write_text(
        f"id: {name}\ndomain: tests\nbrief: {text}\ngrader:\n  secret: never read\n"
    )


def a_trace(**changes: object) -> Trace:
    base = Trace(
        traced=True,
        cards=1,
        judged=1,
        awaiting=0,
        no_brief=0,
        numbers=3,
        resolved=3,
        untraced=(),
        agent_measurements=(),
        strict_pass=Share(numerator=1, denominator=2),
        coverage=Share(numerator=2, denominator=2),
    )
    return base.model_copy(update=changes)


def a_result(brief_id: str, trace: Trace | None, **changes: object) -> BriefResult:
    base = BriefResult(
        id=brief_id,
        domain="tests",
        status="finished",
        model="m",
        cost_usd=0.5,
        turns=3,
        seconds=10,
        note=None,
        trace=trace,
        friction=Friction(confirmation_pages=2, ask_calls=2, minutes_to_first_scorecard=1.5),
    )
    return base.model_copy(update=changes)


def a_home(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    variants = home / ".cad" / "variants"
    variants.mkdir(parents=True)
    return home, variants


def test_the_set_reads_briefs_by_id_and_skips_files_that_are_not_one(tmp_path: Path) -> None:
    write_brief(tmp_path, "bracket-01", "a bracket")
    (tmp_path / "briefs.yaml").write_text("version: 1\nbriefs: []\n")
    found, skipped = load_set(tmp_path)
    assert [(one.id, one.text) for one in found] == [("bracket-01", "a bracket")]
    assert skipped == ["briefs.yaml"]
    assert "never read" not in prompt_for(found[0])


def test_a_brief_file_must_be_named_for_its_id(tmp_path: Path) -> None:
    write_brief(tmp_path, "one", "x")
    (tmp_path / "one.yaml").rename(tmp_path / "two.yaml")
    with pytest.raises(ValueError, match="name the file"):
        load_set(tmp_path)


def test_friction_counts_the_pages_the_person_opened(tmp_path: Path) -> None:
    log = tmp_path / "human.jsonl"
    entries: list[dict[str, object]] = [
        {"step": "page", "sections": [{}]},
        {"step": "confirm"},
        {"step": "page"},
    ]
    log.write_text("".join(json.dumps(one) + "\n" for one in entries))
    assert read_pages(log).shown == 2
    assert read_pages(tmp_path / "missing.jsonl").shown == 0


def test_friction_reports_a_person_log_failure(tmp_path: Path) -> None:
    log = tmp_path / "human.jsonl"
    log.write_text(json.dumps({"error": "URLError: refused"}) + "\n")
    assert read_pages(log).errors == ("URLError: refused",)


def test_minutes_run_from_the_first_brief_to_the_earliest_scorecard(tmp_path: Path) -> None:
    home, variants = a_home(tmp_path)
    brief = home / ".cad" / "briefs" / "b1" / "brief.signed"
    brief.parent.mkdir(parents=True)
    brief.write_text("x")
    later = variants / VARIANT_ID
    later.mkdir()
    (later / SCORECARD).write_text("{}")
    os.utime(brief, (1000, 1000))
    os.utime(later / SCORECARD, (1150, 1150))
    kept = home / ".cad" / "briefs"
    assert minutes_to_first_scorecard(kept, variants, 200) == pytest.approx(2.5)
    assert minutes_to_first_scorecard(kept, tmp_path / "none", 200) is None


def test_minutes_are_dropped_when_the_clock_ran_past_the_session(tmp_path: Path) -> None:
    home, variants = a_home(tmp_path)
    brief = home / ".cad" / "briefs" / "b1" / "brief.signed"
    brief.parent.mkdir(parents=True)
    brief.write_text("x")
    (variants / VARIANT_ID).mkdir()
    card = variants / VARIANT_ID / SCORECARD
    card.write_text("{}")
    later = brief.stat().st_mtime + 900
    os.utime(card, (later, later))
    assert minutes_to_first_scorecard(home / ".cad" / "briefs", variants, 90) is None


def test_a_session_that_stored_nothing_is_not_traced_and_says_why(tmp_path: Path) -> None:
    home, _ = a_home(tmp_path)
    traced = trace_session(home)
    assert not traced.traced
    assert traced.untraced == (NO_CARD,)


def a_home_with_a_build(tmp_path: Path) -> tuple[Path, Path]:
    home, variants = a_home(tmp_path)
    entry.save(
        variants, entry.VariantId(VARIANT_ID), "x = 1\n", Build(outcome=Built(), output=""), BREP
    )
    (variants / VARIANT_ID / entry.STEP).write_bytes(STEP)
    return home, variants


def test_a_card_judged_against_a_confirmed_brief_is_traced(tmp_path: Path) -> None:
    home, variants = a_home_with_a_build(tmp_path)
    roots = Roots(home / ".cad" / "briefs", home / ".cad" / "projects")
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    put(variants, judged_card(confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY))))
    traced = trace_session(home)
    assert traced.traced, traced.untraced
    assert (traced.strict_pass, traced.coverage) == (
        Share(numerator=0, denominator=2),
        Share(numerator=1, denominator=2),
    )


def test_rates_count_the_requirements_of_the_last_card_once(tmp_path: Path) -> None:
    home, variants = a_home_with_a_build(tmp_path)
    roots = Roots(home / ".cad" / "briefs", home / ".cad" / "projects")
    brief_id = briefs.create_brief(roots, BRIEF_TEXT, new_project_id()).id
    card = judged_card(confirm_on_page(roots, brief_id, drafts(LIGHT, FRIENDLY)))
    put(variants, card)
    second = entry.VariantId("fedcba9876543210")
    entry.save(variants, second, "x = 2\n", Build(outcome=Built(), output=""), BREP)
    (variants / second / entry.STEP).write_bytes(STEP)
    (variants / second / SCORECARD).write_text(
        card.model_copy(update={"variant_id": second}).model_dump_json()
    )
    traced = trace_session(home)
    assert traced.cards == 2
    assert traced.coverage == Share(numerator=1, denominator=2)


def test_a_session_failure_names_the_line_that_says_why() -> None:
    output = "init: cad connected\nresult: a reply\ntools outside cad: build_variant\n"
    assert failure_note(output) == "tools outside cad: build_variant"
    assert failure_note("claude blew up") == "claude blew up"
    assert failure_note("") == "no output"


def test_a_card_with_no_brief_is_not_traced(tmp_path: Path) -> None:
    home, variants = a_home_with_a_build(tmp_path)
    put(variants, genuine_card())
    traced = trace_session(home)
    assert not traced.traced
    assert "1 card(s) scored with no brief" in traced.untraced


def test_the_summary_pools_requirements_and_names_untraced_numbers() -> None:
    results = [
        a_result("a", a_trace()),
        a_result(
            "b",
            a_trace(
                traced=False,
                untraced=("v1: mass.volume = 3: Stale old",),
                strict_pass=Share(numerator=0, denominator=4),
                coverage=Share(numerator=1, denominator=4),
            ),
        ),
        a_result("c", None, status="session_failed", note="timed out"),
    ]
    summary = summarize(results, ["d"], "sonnet")
    assert summary.overall.traced == 1
    assert (summary.overall.finished, summary.overall.session_failed, summary.overall.not_run) == (
        2,
        1,
        1,
    )
    assert summary.overall.strict_pass == Share(numerator=1, denominator=6)
    assert summary.overall.coverage == Share(numerator=3, denominator=6)
    text = markdown(summary, ["d"])
    assert "v1: mass.volume = 3: Stale old" in text
    assert "SESSION FAILED: timed out" in text
    assert "| d | - | not run" in text


def stub_session(monkeypatch: pytest.MonkeyPatch, *, failing: set[str]) -> list[str]:
    started: list[str] = []

    def fake(prompt: str, home: Path, transcript: Path, *_: object) -> SessionRun:
        brief_id = home.parent.name
        started.append(brief_id)
        failed = brief_id in failing
        staged = home / ".cad" / "stage" / "cad"
        staged.mkdir(parents=True)
        (staged / "mass.py").write_text("x")
        for path in (staged / "mass.py", staged, staged.parent):
            path.chmod(0o500)
        facts = SessionFacts("m", 0.1, 2, 1, 4, is_error=failed)
        return SessionRun(1 if failed else 0, False, "boom", facts)

    monkeypatch.setattr(run, "run_session", fake)
    return started


def test_a_rerun_skips_finished_briefs_and_runs_failed_ones_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    briefs_dir, out = tmp_path / "set", tmp_path / "out"
    briefs_dir.mkdir()
    for name in ("one", "two"):
        write_brief(briefs_dir, name, "x")
    arguments = ["--briefs", str(briefs_dir), "--out", str(out)]
    started = stub_session(monkeypatch, failing={"two"})
    assert run.main(arguments) == 1
    assert sorted(started) == ["one", "two"]
    assert is_finished(out, "one")
    assert not is_finished(out, "two")
    started.clear()
    stub_session_again = stub_session(monkeypatch, failing=set())
    assert run.main(arguments) == 0
    assert stub_session_again == ["two"]
    assert json.loads((out / "summary.json").read_text())["overall"]["finished"] == 2


def test_only_runs_the_named_briefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    briefs_dir, out = tmp_path / "set", tmp_path / "out"
    briefs_dir.mkdir()
    for name in ("one", "two"):
        write_brief(briefs_dir, name, "x")
    started = stub_session(monkeypatch, failing=set())
    run.main(["--briefs", str(briefs_dir), "--out", str(out), "--only", "two"])
    assert started == ["two"]

"""A brief run again into the same `--out` keeps its earlier try. A call Claude Code refused as no
such tool is counted apart as the model's friction, and a check job the session's end cut off is
named apart."""

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest
import run
from outcome import BriefResult, Counted, Friction, Share, Trace, read_results
from session import SessionFacts, SessionRun, read_transcript
from summary import markdown, summarize

TRANSCRIPTS = Path(__file__).parents[1] / "verify" / "transcripts"


def test_a_rerun_keeps_each_earlier_try_beside_the_next(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    briefs_dir, out = tmp_path / "set", tmp_path / "out"
    briefs_dir.mkdir()
    (briefs_dir / "one.yaml").write_text("id: one\ndomain: tests\nbrief: x\n")
    tries: list[int] = []

    def session(prompt: str, home: Path, transcript: Path, *_: object) -> SessionRun:
        tries.append(len(tries) + 1)
        transcript.write_text(f"try {tries[-1]}")
        staged = home / ".cad" / "stage"
        staged.mkdir(parents=True)
        (staged / "mass.py").write_text(f"try {tries[-1]}")
        staged.chmod(0o500)
        return SessionRun(1, False, "boom", SessionFacts("m", 0.1, 2, 0, 1, is_error=True))

    monkeypatch.setattr(run, "run_session", session)
    arguments = ["--briefs", str(briefs_dir), "--out", str(out), "--only", "one"]
    for _ in range(3):
        assert run.main(arguments) == 1
    directory = out / "one"
    assert (directory / "transcript.json").read_text() == "try 3"
    for earlier in (1, 2):
        kept = directory / f"try-{earlier}"
        assert (kept / "transcript.json").read_text() == f"try {earlier}"
        assert (kept / "home" / ".cad" / "stage" / "mass.py").read_text() == f"try {earlier}"
        assert json.loads((kept / "result.json").read_text())["status"] == "session_failed"
    assert not (directory / "try-1" / "try-2").exists()
    assert [one.id for one in read_results(out, ["one"])] == ["one"]


def test_the_session_counts_the_calls_outside_cad(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.json"
    shutil.copy(TRANSCRIPTS / "refused_unprefixed.json", transcript)
    facts = read_transcript(transcript)
    assert facts.refused_calls == 1
    assert facts.tool_calls > facts.refused_calls


def test_the_summary_pools_refused_calls_and_cut_off_jobs_of_finished_briefs() -> None:
    trace = Trace(
        traced=True,
        shown=Counted(cards=1, judged=1, numbers=1, resolved=1),
        read=Counted(cards=1, judged=1, numbers=1, resolved=1),
        awaiting=0,
        no_brief=0,
        untraced=(),
        agent_measurements=(),
        strict_pass=Share(numerator=1, denominator=1),
        coverage=Share(numerator=1, denominator=1),
        agent_coverage=Share(numerator=0, denominator=1),
        cut_off=("v1: fea for 557d8d82",),
    )

    def result(
        brief_id: str, refused: int, status: Literal["finished", "session_failed"] = "finished"
    ) -> BriefResult:
        return BriefResult(
            id=brief_id,
            domain="tests",
            status=status,
            model="m",
            cost_usd=0.5,
            turns=3,
            seconds=10,
            note=None,
            trace=trace if status == "finished" else None,
            friction=Friction(
                confirmation_pages=1,
                ask_calls=1,
                minutes_to_first_result=1.0,
                refused_tool_calls=refused,
            ),
        )

    results = [result("a", 2), result("b", 1), result("c", 5, "session_failed")]
    summary = summarize(results, [], "m")
    assert (summary.overall.refused_tool_calls, summary.overall.cut_off) == (3, 2)
    text = markdown(summary, [])
    assert "tool calls Claude Code refused as no such tool, model friction: 3" in text
    assert "check jobs still running when the session ended, cut off: 2" in text
    assert "## Cut off in a\n- v1: fea for 557d8d82" in text

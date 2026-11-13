"""A stress result names the faces the check fixed and loaded. On a card the session was shown,
each face index traces only when the signed job result holds the same index at the same place."""

import json
from pathlib import Path

import pytest
from tracefacts import trace_session

from cad.checks.result import Faces, Verdict, Where
from tests.support.background import a_scoring, fea_of, ran, sandbox
from tests.support.cards import transcript_of, write_transcript

FACES = Where(support=(10, 11), load=(4,), displacement=Faces(support=(2,), load=(6,)))


def test_the_faces_of_a_signed_stress_result_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox(monkeypatch, ran(Verdict.PASS, where=FACES))
    scoring = a_scoring(tmp_path, stated=True)
    card = scoring.score()
    assert fea_of(card)["where"] == FACES.model_dump(mode="json")
    write_transcript(scoring.variants, json.dumps(card))
    traced = trace_session(scoring.home, transcript_of(scoring.variants))
    assert traced.traced, traced.untraced
    assert traced.shown.numbers == traced.shown.resolved
    assert traced.read.numbers == traced.read.resolved


@pytest.mark.parametrize(
    ("keys", "index", "forged"),
    [(("support",), 1, 12), (("load",), 0, 5), (("displacement", "load"), 0, 7)],
    ids=["support", "load", "displacement"],
)
def test_a_face_the_signed_job_result_does_not_hold_is_untraced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    keys: tuple[str, ...],
    index: int,
    forged: int,
) -> None:
    sandbox(monkeypatch, ran(Verdict.PASS, where=FACES))
    scoring = a_scoring(tmp_path, stated=True)
    card = scoring.score()
    faces = fea_of(card)["where"]
    for key in keys:
        faces = faces[key]
    original, faces[index] = faces[index], forged
    write_transcript(scoring.variants, json.dumps(card))
    traced = trace_session(scoring.home, transcript_of(scoring.variants))
    assert not traced.traced
    path = ".".join(keys) + f"[{index}]"
    assert any(
        f"where.{path} = {forged}: Unresolved face {path} is {forged} on the card, but the "
        f"signed job result holds {original}" in line
        for line in traced.untraced
    ), traced.untraced
    assert any(
        "Unsigned the card's fea for" in line
        and "differs from the signed job result in where" in line
        for line in traced.untraced
    ), traced.untraced

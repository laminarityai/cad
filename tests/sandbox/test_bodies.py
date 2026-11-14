import json
from base64 import b64encode

import pytest

from cad.sandbox.bodies import MAX_BODIES, MAX_SOLIDS, Body
from cad.sandbox.container import Attended, ContainerState, Job
from cad.sandbox.host import Artifacts, classify
from cad.sandbox.outcome import Built, NoResult

JOB = Job("build", "sha256:sandbox", (), b"", wall_seconds=60)


def verdict_of(bodies: object) -> Artifacts | NoResult:
    report = json.dumps({"kind": "built", "brep": b64encode(b"brep").decode(), "bodies": bodies})
    seen = Attended(killed_at_deadline=False, report=report.encode(), output="")
    ran = classify(
        seen, ContainerState(Status="exited", ExitCode=0, OOMKilled=False, Error=""), JOB
    )
    assert isinstance(ran, Artifacts | NoResult), ran
    return ran


def refusal(bodies: object) -> str:
    ran = verdict_of(bodies)
    assert isinstance(ran, NoResult), ran
    return ran.reason


def test_a_result_of_one_solid_is_one_unnamed_body() -> None:
    assert verdict_of([]) == Artifacts(b"brep", Built())


def test_solids_that_share_a_label_are_one_body_numbered_as_the_kernel_numbers_them() -> None:
    ran = verdict_of(["plate", "gear", "gear", "spacer", "gear"])
    assert isinstance(ran, Artifacts)
    assert ran.built.bodies == (
        Body(name="plate", solids=(0,)),
        Body(name="gear", solids=(1, 2, 4)),
        Body(name="spacer", solids=(3,)),
    )


def test_a_solid_with_no_label_refuses_the_build_and_says_how_to_name_it() -> None:
    reason = refusal(["plate", None, None])
    assert "2 of the 3 solids of `result` have no label (solids 1, 2)" in reason
    assert "Compound(children=[...])" in reason
    assert "fuse" in reason


def test_more_solids_than_a_variant_holds_refuse_the_build() -> None:
    reason = refusal(["gear"] * (MAX_SOLIDS + 1))
    assert f"`result` has {MAX_SOLIDS + 1} solids, and a variant holds at most {MAX_SOLIDS}" in (
        reason
    )


def test_more_bodies_than_a_variant_holds_refuse_the_build() -> None:
    names = [f"part-{n}" for n in range(MAX_BODIES + 1)]
    reason = refusal(names)
    assert f"{MAX_BODIES + 1} bodies, and a variant holds at most {MAX_BODIES}" in reason


@pytest.mark.parametrize(
    "name", ["Steel gear", "gear plate", "1gear", "a" * 33, "gear_1", "", "-gear"]
)
def test_a_label_that_is_not_a_body_name_refuses_the_build_and_names_the_pattern(
    name: str,
) -> None:
    reason = refusal(["plate", name])
    assert "lowercase letter" in reason
    assert "32 characters" in reason


def test_a_long_bad_label_is_cut_short_in_the_refusal() -> None:
    assert len(refusal(["plate", "X" * 10_000])) < 600


@pytest.mark.parametrize("raw", ["TypeError: no children", {"plate": [0]}, [3, 4], "x" * 5000])
def test_a_body_list_the_runner_could_not_read_refuses_the_build(raw: object) -> None:
    reason = refusal(raw)
    assert reason.startswith("the bodies of `result` could not be read")
    assert len(reason) < 600


def test_a_body_name_never_carries_a_colour() -> None:
    assert set(Body.model_fields) == {"name", "solids"}

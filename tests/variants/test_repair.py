from collections.abc import Callable
from pathlib import Path

import pytest

from cad.sandbox import builder, image
from cad.sandbox.builder import Artifacts, Run
from cad.sandbox.outcome import Build, Built, NoResult, SandboxUnavailable
from cad.variants import entry, repair
from cad.variants.entry import OutdatedVariant, StaleVariant, VariantId, open_entry, variant_id

TAG = "cad-sandbox:test"
OLD_TAG = "cad-sandbox:before-an-update"
CODE = "result = Box(1, 1, 1)\n"
BREP = b"CASCADE Topology V3, (c) Open Cascade\n"
RESULT = "jobs/0123.signed"


def stored(root: Path, tag: str = TAG, code: str = CODE) -> VariantId:
    vid = variant_id(code, tag)
    entry.save(root, vid, code, Build(outcome=Built(), output=""), BREP)
    (root / vid / RESULT).parent.mkdir()
    (root / vid / RESULT).write_bytes(b"a signed check result")
    (root / vid / entry.STEP).write_bytes(b"a STEP of the shape")
    return vid


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every code the fake sandbox built. It builds BREP, the bytes the store first held, except
    for a code that says "another"."""
    built: list[str] = []

    def build(code: str, image_id: str, *, wall_seconds: int, parts: object) -> Run:
        built.append(code)
        return Run(Artifacts(b"another shape" if "another" in code else BREP, Built()), "")

    def current_image(tag: str) -> str:
        return f"sha256:{tag}"

    monkeypatch.setattr(builder, "build", build)
    monkeypatch.setattr(image, "current_image", current_image)
    return built


def lose(shape: Path) -> None:
    shape.unlink()


def alter(shape: Path) -> None:
    shape.write_bytes(b"half a shape")


def edit_code(held: Path) -> None:
    held.joinpath(entry.CODE).write_text(CODE + "# edited\n")


def forge_signature(held: Path) -> None:
    held.joinpath(entry.MAC).write_bytes(b"0" * 64)


def lose_record(held: Path) -> None:
    held.joinpath(entry.MANIFEST).unlink()


@pytest.mark.parametrize("damage", [lose, alter])
def test_an_entry_whose_shape_is_damaged_is_rebuilt_from_its_signed_code_with_its_results(
    tmp_path: Path, builds: list[str], damage: Callable[[Path], None]
) -> None:
    vid = stored(tmp_path)
    damage(tmp_path / vid / entry.BREP)
    repair.heal(tmp_path, vid, TAG)
    held = open_entry(tmp_path, vid, TAG)
    assert (held.id, held.brep, builds) == (vid, BREP, [CODE])
    assert (tmp_path / vid / RESULT).read_bytes() == b"a signed check result"
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []
    repair.heal(tmp_path, vid, TAG)
    assert open_entry(tmp_path, vid, TAG) == held
    assert builds == [CODE]


def test_a_rebuild_that_is_not_the_signed_shape_is_refused_and_not_kept(
    tmp_path: Path, builds: list[str]
) -> None:
    code = CODE + "# another\n"
    vid = stored(tmp_path, code=code)
    (tmp_path / vid / entry.BREP).unlink()
    with pytest.raises(StaleVariant, match="did not build the same shape again"):
        repair.heal(tmp_path, vid, TAG)
    assert builds == [code]
    assert not (tmp_path / vid / entry.BREP).exists()


@pytest.mark.parametrize(
    ("damage", "refusal"),
    [
        (edit_code, "code.py"),
        (forge_signature, "integrity check"),
        (lose_record, "integrity check"),
    ],
)
def test_an_entry_without_the_code_its_key_signed_is_refused_and_nothing_is_built(
    tmp_path: Path, builds: list[str], damage: Callable[[Path], None], refusal: str
) -> None:
    vid = stored(tmp_path)
    (tmp_path / vid / entry.BREP).unlink()
    damage(tmp_path / vid)
    repair.heal(tmp_path, vid, TAG)
    with pytest.raises(StaleVariant, match=refusal):
        open_entry(tmp_path, vid, TAG)
    assert builds == []


def test_a_rebuild_that_cannot_run_leaves_the_damaged_entry_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vid = stored(tmp_path)
    (tmp_path / vid / entry.BREP).unlink()
    kept = sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / vid).rglob("*"))

    def down(tag: str) -> str:
        raise SandboxUnavailable("docker is not reachable")

    monkeypatch.setattr(image, "current_image", down)
    with pytest.raises(SandboxUnavailable):
        repair.heal(tmp_path, vid, TAG)
    assert sorted(p.relative_to(tmp_path).as_posix() for p in (tmp_path / vid).rglob("*")) == kept


def test_an_outdated_entry_loses_its_shape_files_once_this_sandbox_built_its_code(
    tmp_path: Path,
) -> None:
    old = stored(tmp_path, OLD_TAG)
    stored(tmp_path)
    with pytest.raises(OutdatedVariant) as before:
        open_entry(tmp_path, old, TAG)
    assert repair.collect_outdated(tmp_path, old, TAG)
    assert sorted(p.name for p in (tmp_path / old).iterdir()) == [
        "build.json",
        "build.mac",
        "code.py",
        "jobs",
    ]
    assert (tmp_path / old / RESULT).read_bytes() == b"a signed check result"
    with pytest.raises(OutdatedVariant) as after:
        open_entry(tmp_path, old, TAG)
    assert (str(after.value), after.value.code) == (str(before.value), before.value.code)


def no_current_build(root: Path) -> None:
    del root


def current_build_failed(root: Path) -> None:
    vid = variant_id(CODE, TAG)
    entry.save(root, vid, CODE, Build(outcome=NoResult(reason="no result"), output=""), None)


def current_build_damaged(root: Path) -> None:
    (root / stored(root) / entry.BREP).unlink()


def old_code_altered(root: Path) -> None:
    stored(root)
    (root / variant_id(CODE, OLD_TAG) / entry.CODE).write_text(CODE + "# edited\n")


@pytest.mark.parametrize(
    "state", [no_current_build, current_build_failed, current_build_damaged, old_code_altered]
)
def test_an_outdated_entry_keeps_its_shape_files_unless_a_whole_current_build_of_its_code_exists(
    tmp_path: Path, state: Callable[[Path], None]
) -> None:
    old = stored(tmp_path, OLD_TAG)
    state(tmp_path)
    assert not repair.collect_outdated(tmp_path, old, TAG)
    assert (tmp_path / old / entry.BREP).read_bytes() == BREP


def test_a_current_entry_is_never_collected(tmp_path: Path) -> None:
    vid = stored(tmp_path)
    assert not repair.collect_outdated(tmp_path, vid, TAG)
    assert open_entry(tmp_path, vid, TAG).brep == BREP


def test_a_score_collects_every_outdated_build_of_its_code_and_keeps_the_rest(
    tmp_path: Path,
) -> None:
    old = stored(tmp_path, OLD_TAG)
    other = stored(tmp_path, OLD_TAG, code=CODE + "# another\n")
    current = stored(tmp_path)
    repair.collect_beside(tmp_path, current, TAG)
    assert not (tmp_path / old / entry.BREP).exists()
    assert (tmp_path / other / entry.BREP).exists()
    assert open_entry(tmp_path, current, TAG).brep == BREP

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.briefs import store as briefs
from cad.records import signed
from cad.records.roots import Roots, project_store
from cad.sandbox.outcome import Built
from cad.variant_sets.model import (
    MAX_MEMBERS,
    Joined,
    Member,
    NotConfirmed,
    NotJoined,
    SetBuildResult,
    SetBusy,
    SetFull,
    SetKey,
    SetRefused,
    TamperedSet,
    code_sha256,
)
from cad.variants import store as variants
from cad.variants.entry import VariantId

MAX_MEMBER_BYTES: Final = signed.MAX_RECORD_BYTES // 2
LOG = logging.getLogger(__name__)


def build_into_set(roots: Roots, variants_root: Path, brief_id: str, code: str) -> SetBuildResult:
    root = roots.projects
    key = confirmed_key(roots, brief_id)
    held = members(root, key)
    sha256 = code_sha256(code)
    if len(held) >= MAX_MEMBERS and all(m.code_sha256 != sha256 for m in held):
        raise _full(key)
    _record(code, VariantId("0" * 16), key)
    built = variants.build_variant(code, variants_root)
    joined = join(root, key, code, built.variant_id) if built.outcome == Built() else NotJoined()
    return SetBuildResult(
        variant_id=built.variant_id, outcome=built.outcome, output=built.output, variant_set=joined
    )


def confirmed_key(roots: Roots, brief_id: str) -> SetKey:
    state = briefs.read_state(roots, brief_id)
    confirmed = state.confirmed
    if confirmed is None or confirmed.answered is None:
        raise NotConfirmed(
            f"brief {state.brief.id} has no confirmed requirements, so it has no variant set "
            "yet. Call ask_to_confirm with its project, and build with this brief_id once the user "
            "confirms. A build without brief_id joins no set."
        )
    return SetKey(state.brief.project, state.brief.id, confirmed.answered.sha256)


def join(root: Path, key: SetKey, code: str, built_as: VariantId) -> Joined:
    sha256 = code_sha256(code)
    record = _record(code, built_as, key)
    directory = _directory(root, key)
    slot: int | None = None
    full = False

    def next_member(existing: tuple[bytes, ...]) -> bytes | None:
        nonlocal slot, full
        held = [m.code_sha256 for m in _parse(key, directory, existing)]
        slot = held.index(sha256) + 1 if sha256 in held else None
        full = slot is None and len(held) >= MAX_MEMBERS
        return None if slot is not None or full else record

    with _without_host_paths(key, directory):
        directory.mkdir(parents=True, exist_ok=True)
        appended = signed.append(project_store(root), directory, _member_slot(key), next_member)
    if isinstance(appended, signed.Appended):
        return Joined(slot=appended.number, already_member=False)
    if full:
        raise _full(key, built_as)
    if slot is None:
        raise TamperedSet(_report(key, directory))
    return Joined(slot=slot, already_member=True)


def _record(code: str, built_as: VariantId, key: SetKey) -> bytes:
    record = (
        Member(
            code=code, code_sha256=code_sha256(code), built_as=built_as, joined_at=datetime.now(UTC)
        )
        .model_dump_json()
        .encode()
    )
    if len(record) > MAX_MEMBER_BYTES:
        raise SetRefused(f"this code is too large to keep in the variant set of {key.brief_id}")
    return record


def members(root: Path, key: SetKey) -> tuple[Member, ...]:
    directory = _directory(root, key)
    with _without_host_paths(key, directory):
        _refuse_the_old_layout(root, key)
        if not signed.is_directory(directory):
            return ()
        records = signed.read_numbered(project_store(root), directory, _member_slot(key))
    if records is None:
        raise TamperedSet(_report(key, directory))
    return _parse(key, directory, records)


def _refuse_the_old_layout(root: Path, key: SetKey) -> None:
    """Sets from before each brief had its own directory sit at <project>/sets/<decision>/members.

    This version does not read them, so it refuses rather than ignore them without a word.
    """
    sets = root / key.project / "sets"
    old = min(sets.glob("*/members"), default=None) if signed.is_directory(sets) else None
    if old is None:
        return
    LOG.error("%s holds variant sets in a layout this version does not read", old)
    raise SetRefused(
        f"the project store holds variant sets in an old layout, at {old.relative_to(root)}, "
        "which this version does not read; the operator must move or delete that directory"
    )


def _parse(key: SetKey, directory: Path, records: tuple[bytes, ...]) -> tuple[Member, ...]:
    try:
        return tuple(Member.model_validate_json(record) for record in records)
    except ValidationError as error:
        raise TamperedSet(_report(key, directory)) from error


@contextmanager
def _without_host_paths(key: SetKey, directory: Path) -> Generator[None]:
    try:
        yield
    except signed.Tampered as error:
        raise TamperedSet(_report(key, directory)) from error
    except signed.Contended as error:
        raise SetBusy(
            f"the variant set of brief {key.brief_id} is being joined by several builds at "
            "once; build again"
        ) from error
    except OSError as error:
        LOG.error("cannot use %s: %s", directory, error)
        raise signed.StoreUnusable(
            f"cannot use the variant set store for brief {key.brief_id}: {type(error).__name__}"
        ) from error


def _directory(root: Path, key: SetKey) -> Path:
    return root / key.project / "sets" / key.brief_id / key.decision_sha256 / "members"


def _member_slot(key: SetKey) -> Callable[[int], str]:
    return lambda number: (
        f"{key.project}/sets/{key.brief_id}/{key.decision_sha256}/members/{number}"
    )


def _full(key: SetKey, built_as: VariantId | None = None) -> SetFull:
    advice = (
        "Score those variants and show them to the user to compare. "
        "Requirements the user confirms later start a new, empty set."
    )
    held = f"the variant set of brief {key.brief_id} holds {MAX_MEMBERS} variants, its limit"
    if built_as is None:
        return SetFull(f"{held}, so this code was not built. {advice}")
    return SetFull(
        f"{held}. The set filled while this code was building: it was built as variant "
        f"{built_as} and is stored, but it did not join the set. {advice}"
    )


def _report(key: SetKey, directory: Path) -> str:
    LOG.error("%s holds a variant set record this store did not sign or cannot read", directory)
    return (
        f"the variant set of brief {key.brief_id} has a record this store did not sign or "
        "cannot read; the operator must delete that set from the variant set store"
    )

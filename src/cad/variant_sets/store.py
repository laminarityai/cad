import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cad.briefs import store as briefs
from cad.briefs.model import BriefId
from cad.checks.lanes import LANES, Lanes
from cad.projects.model import PROJECT_ID, ProjectId
from cad.records import files, signed
from cad.records.roots import Roots, project_store
from cad.sandbox.bodies import Bodies
from cad.sandbox.outcome import Built
from cad.variant_sets.model import (
    MAX_MEMBERS,
    BodyMaterialsRefused,
    Chosen,
    Joined,
    MaterialMissing,
    Member,
    NotJoined,
    Option,
    Resolve,
    Revision,
    SetBuildResult,
    SetBusy,
    SetFull,
    SetKey,
    SetRefused,
    SlotRefused,
    TamperedSet,
    code_sha256,
    group,
)
from cad.variant_sets.placement import Design, Placement, place, shown
from cad.variants import store as variants
from cad.variants.entry import VariantId

MAX_MEMBER_BYTES: Final = files.MAX_RECORD_BYTES // 2
LOG = logging.getLogger(__name__)


def build_into_set(
    roots: Roots,
    variants_root: Path,
    brief_id: str,
    code: str,
    slot: int | None,
    resolve: Resolve,
    option: Option | None = None,
    lanes: Lanes = LANES,
    on_built: Callable[[VariantId], None] = lambda _: None,
) -> SetBuildResult:
    """`on_built` runs once the build returns, before the join, so a join the set refuses
    still leaves the build counted."""
    root = roots.projects
    key = set_key(roots, brief_id)
    held = members(root, key)
    sha256 = code_sha256(code)
    try:
        design = _resolved(held, sha256, slot, resolve, option)
        place(held, sha256, design, slot)
    except SetFull:
        raise _full(key) from None
    _record(code, 1, VariantId("0" * 16), key, design)
    built = variants.build_variant(code, variants_root)
    on_built(built.variant_id)
    joined = (
        join(root, key, code, built.variant_id, slot, resolve, option, built.outcome.bodies)
        if isinstance(built.outcome, Built)
        else NotJoined()
    )
    if isinstance(joined, Joined) and not joined.already_member:
        _drop_replaced(root, key, variants_root, joined, lanes)
    return SetBuildResult(
        variant_id=built.variant_id, outcome=built.outcome, output=built.output, variant_set=joined
    )


def _drop_replaced(
    root: Path, key: SetKey, variants_root: Path, joined: Joined, lanes: Lanes
) -> None:
    member = next((m for m in members(root, key) if m.slot == joined.slot), None)
    if member is None or len(member.revisions) < 2:
        return
    earlier = {revision.built_as for revision in member.revisions[:-1]}

    def unshown() -> set[VariantId]:
        return earlier - {held.latest.built_as for _, held in account_slots(root)}

    try:
        lanes.drop_unstarted(variants_root, unshown)
    except SetRefused as error:
        LOG.warning("no queued check is dropped: %s", error)


def set_key(roots: Roots, brief_id: str) -> SetKey:
    brief = briefs.read_brief(roots, brief_id)
    return SetKey(brief.project, brief.id)


def _no_choice(previous: Revision | None, bodies: Bodies | None) -> Chosen:
    return Chosen()


def _resolved(
    held: tuple[Member, ...],
    sha256: str,
    slot: int | None,
    resolve: Resolve,
    option: Option | None,
    bodies: Bodies | None = None,
) -> Design:
    slot_now = shown(held, sha256, slot)
    latest = None if slot_now is None else slot_now.latest
    return Design(
        chosen=resolve(latest, bodies),
        option=option or (None if latest is None else latest.option),
    )


def join(
    root: Path,
    key: SetKey,
    code: str,
    built_as: VariantId,
    slot: int | None = None,
    resolve: Resolve = _no_choice,
    option: Option | None = None,
    bodies: Bodies = (),
) -> Joined:
    """Make `code` what `slot` shows, as a new revision. With no slot, new code takes a free one.

    `resolve` runs on the log being appended to, so a choice made by a build that finished first
    is the one it sees. It reads `bodies`, the bodies the code built, so a material that names a
    body the code did not build joins nothing."""
    sha256 = code_sha256(code)
    directory = _directory(root, key)
    outcome: list[Placement | SetRefused] = []

    def next_revision(existing: tuple[bytes, ...]) -> bytes | None:
        outcome.clear()
        try:
            held = group(_parse(key, directory, existing))
            design = _resolved(held, sha256, slot, resolve, option, bodies)
            placed = place(held, sha256, design, slot)
        except SetFull:
            outcome.append(_full(key, built_as))
            return None
        except (SlotRefused, MaterialMissing, BodyMaterialsRefused) as error:
            kept = f"It was built as variant {built_as} and is stored."
            outcome.append(type(error)(f"{str(error).rstrip('.')}. {kept}"))
            return None
        outcome.append(placed)
        return None if placed.unchanged else _record(code, placed.slot, built_as, key, design)

    with _without_host_paths(key, directory):
        signed.append(project_store(root), directory, _revision_slot(key), next_revision)
    [result] = outcome
    if isinstance(result, SetRefused):
        raise result
    return Joined(slot=result.slot, revision=result.revision, already_member=result.unchanged)


def _record(code: str, slot: int, built_as: VariantId, key: SetKey, design: Design) -> bytes:
    record = (
        Revision(
            slot=slot,
            code=code,
            code_sha256=code_sha256(code),
            built_as=built_as,
            joined_at=datetime.now(UTC),
            material=design.chosen.material,
            option=design.option,
            materials=design.chosen.materials,
        )
        .model_dump_json()
        .encode()
    )
    if len(record) > MAX_MEMBER_BYTES:
        raise SetRefused(f"this code is too large to keep in the variant set of {key.brief_id}")
    return record


def showing(root: Path, key: SetKey, variant_id: str, image_tag: str) -> Revision | None:
    """The latest revision of the slot that shows `variant_id`, with the material the agent chose
    for it."""
    for member in members(root, key):
        if variant_id in (member.latest.built_as, member.latest.live_id(image_tag)):
            return member.latest
    return None


def project_slots(root: Path, project: ProjectId) -> tuple[tuple[SetKey, Member], ...]:
    """Every slot of every variant set in the project, with the set that holds it."""
    sets = root / project / "sets"
    if not files.is_directory(sets):
        return ()
    found: list[tuple[SetKey, Member]] = []
    for revisions in sorted(sets.glob("*/revisions")):
        key = SetKey(project, BriefId(revisions.parent.name))
        found.extend((key, member) for member in members(root, key))
    return tuple(found)


def account_slots(root: Path) -> tuple[tuple[SetKey, Member], ...]:
    if not files.is_directory(root):
        return ()
    projects = sorted(path.name for path in root.iterdir() if PROJECT_ID.fullmatch(path.name))
    return tuple(slot for project in projects for slot in project_slots(root, ProjectId(project)))


def refuse_a_slot_out_of_turn(roots: Roots, brief_id: str, slot: int) -> None:
    """An Auto revision changes a slot its set holds, or takes the next free one. Auto revisions
    are recorded one at a time, so unlike parallel builds they never need a later slot first."""
    key = set_key(roots, brief_id)
    taken = [member.slot for member in members(roots.projects, key)]
    free = next((n for n in range(1, MAX_MEMBERS + 1) if n not in taken), None)
    if slot in taken or slot == free:
        return
    holds = (
        "it holds no variant yet" if not taken else f"it holds slots {', '.join(map(str, taken))}"
    )
    nxt = "" if free is None else f", or takes the next free one, slot {free}"
    raise SlotRefused(
        f"the variant set of brief {key.brief_id} holds no slot {slot}: {holds}. An Auto revision "
        f"changes a slot this set holds{nxt}. A variant in another brief's set is revised by a run "
        "started with auto_start on the brief whose variant set holds it. Nothing was built."
    )


def members(root: Path, key: SetKey) -> tuple[Member, ...]:
    directory = _directory(root, key)
    with _without_host_paths(key, directory):
        if not files.is_directory(directory):
            return ()
        records = signed.read_numbered(project_store(root), directory, _revision_slot(key))
    if records is None:
        raise TamperedSet(_report(key, directory))
    return group(_parse(key, directory, records))


def _parse(key: SetKey, directory: Path, records: tuple[bytes, ...]) -> tuple[Revision, ...]:
    try:
        return tuple(Revision.model_validate_json(record) for record in records)
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
    return root / key.project / "sets" / key.brief_id / "revisions"


def _revision_slot(key: SetKey) -> Callable[[int], str]:
    return lambda number: f"{key.project}/sets/{key.brief_id}/revisions/{number}"


def _full(key: SetKey, built_as: VariantId | None = None) -> SetFull:
    advice = "Score those variants and show them to the user to compare."
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
        f"the variant set of brief {key.brief_id} failed the server's integrity check, so its "
        "options cannot be shown; create a new brief to build options again"
    )

import re
from collections.abc import Mapping, Sequence
from typing import Final

from cad.agent_checks.store import checks_of
from cad.briefs import carry, store
from cad.briefs.bindable import BINDABLE
from cad.briefs.edits import apply_edits, placeholder
from cad.briefs.model import (
    AgentLimit,
    MadeOf,
    MeasureLimit,
    Requirement,
    RequirementId,
    Target,
    deciding_check,
    load_of,
)
from cad.briefs.origins import quoted
from cad.briefs.store import BriefState, ProposalState, Status, TamperedBrief
from cad.briefs.words import describe
from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.confirmations.items import Changes, Editable, Refused, Row, Section
from cad.context_parts.store import stored_parts
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots
from cad.research.overlay import project_table
from cad.sandbox import host

SLOT: Final = re.compile(r"([0-9a-f]{16})/proposal/([1-9][0-9]{0,3})")
TITLE: Final = "Requirements for your brief"
DESCRIBED_NOTE: Final = (
    "The agent described where this part is held and loaded. Confirm only if these words match "
    "how it will be used."
)
REMOVE: Final = "Remove: "
REMOVE_NOTE: Final = "You confirmed this before. Confirming takes it out of your targets."
CONFIRMED_NOTE: Final = "You confirmed this before."
EDITED_NOTE: Final = "You confirmed this before, after you changed it from {before}."
AGENT_DECIDES: Final = (
    "Decided by the agent-written check below once you approve it. Our team has not reviewed it"
)


class Requirements:
    def __init__(self, roots: Roots) -> None:
        self._roots = roots

    @property
    def name(self) -> ItemKindName:
        return "requirements"

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]:
        refs: list[ItemRef] = []
        for brief_id in project_briefs(self._roots, project):
            latest = store.read_state(self._roots, brief_id).latest
            if latest is not None and latest.status is Status.PROPOSED:
                refs.append(latest.ref)
        return tuple(refs)

    def section(self, ref: ItemRef) -> Section:
        state, shown = self._shown(ref)
        text = state.brief.text
        names = plain_names(self._roots, shown.proposal.brief_id)
        before = _confirmed_before(state, shown)
        rows = tuple(
            _row(r, text, names, before.get(r.id, "")) for r in shown.proposal.requirements
        )
        removed = tuple(_removal(r, text, names) for r in _dropped(state, shown))
        return Section(
            title=TITLE, brief_id=shown.proposal.brief_id, context=text, rows=rows + removed
        )

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> Refused | Changes:
        proposed = self._shown(ref)[1].proposal.requirements
        applied = apply_edits(proposed, edits)
        if isinstance(applied, str):
            return Refused(applied)
        return tuple(
            f"{describe(new)} (you changed it from {placeholder(old)})."
            for old, new in zip(proposed, applied, strict=True)
            if new.id != old.id
        )

    def _shown(self, ref: ItemRef) -> tuple[BriefState, ProposalState]:
        match = SLOT.fullmatch(ref.slot)
        if match is None:
            raise TamperedBrief(f"no proposal is stored at {ref.slot!r}")
        state = store.read_state(self._roots, match.group(1))
        shown = state.proposal(int(match.group(2)))
        if shown is None or shown.ref != ref:
            raise TamperedBrief(f"brief {state.brief.id} changed since the page opened")
        return state, shown


def plain_names(roots: Roots, brief_id: str) -> dict[str, str]:
    project = store.read_brief(roots, brief_id).project
    table = project_table(host.materials_table(), roots.projects, project).table
    names = {key: table.name_of(key) for key in table.materials}
    names.update((one.record.id, one.record.name) for one in stored_parts(roots.projects, project))
    names.update((one.sha256, one.check.title) for one in checks_of(roots.projects, project))
    return names


def _editable(requirement: Requirement) -> Editable | None:
    shown = placeholder(requirement)
    return None if shown is None else Editable(row=requirement.id, placeholder=shown)


def _confirmed_before(state: BriefState, shown: ProposalState) -> dict[RequirementId, str]:
    """The note for each row of `shown` that an earlier confirmed set holds, so the card tells a
    carried row from a new one and keeps the person's own change in sight."""
    confirmed = state.confirmed
    if confirmed is None or confirmed.proposal.number >= shown.proposal.number:
        return {}
    changed = carry.edited(state)
    notes: dict[RequirementId, str] = {}
    for one in confirmed.requirements:
        was = changed.get(one.id)
        shown_was = None if was is None else placeholder(was)
        notes[one.id] = (
            CONFIRMED_NOTE if shown_was is None else EDITED_NOTE.format(before=shown_was)
        )
    return notes


def _row(requirement: Requirement, text: str, names: Mapping[str, str], before: str) -> Row:
    source, quote = quoted(text, requirement.origin)
    return Row(
        headline=describe(requirement, names),
        quote=quote,
        source=source,
        decides=_decides(requirement.target),
        editable=_editable(requirement),
        note=" ".join(one for one in (before, _note(requirement.target)) if one),
    )


def _dropped(state: BriefState, shown: ProposalState) -> tuple[Requirement, ...]:
    confirmed = state.confirmed
    kept = {r.id for r in shown.proposal.requirements}
    return tuple(r for r in confirmed.requirements if r.id not in kept) if confirmed else ()


def _removal(requirement: Requirement, text: str, names: Mapping[str, str]) -> Row:
    source, quote = quoted(text, requirement.origin)
    return Row(
        headline=f"{REMOVE}{describe(requirement, names)}",
        quote=quote,
        source=source,
        decides="No check reads it once you confirm",
        note=REMOVE_NOTE,
    )


def _note(target: Target) -> str:
    case = load_of(target)
    return DESCRIBED_NOTE if case is not None and case.described else ""


def _decides(target: Target) -> str:
    if isinstance(target, MadeOf):
        return "Fixes the material that scoring uses"
    if isinstance(target, AgentLimit):
        return AGENT_DECIDES
    check = deciding_check(target)
    if check is None:
        return "No reviewed check: unverified"
    if isinstance(target, MeasureLimit):
        words = BINDABLE[(target.check_id, target.measure)].words
        return f"Decided by the {check} check, which measures {words}"
    return f"Decided by the {check} check"

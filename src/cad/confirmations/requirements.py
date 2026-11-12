import re
from collections.abc import Mapping, Sequence
from typing import Final

from cad.agent_checks.store import checks_of
from cad.briefs import store
from cad.briefs.bindable import BINDABLE
from cad.briefs.edits import apply_edits, placeholder
from cad.briefs.model import (
    AgentLimit,
    MadeOf,
    MeasureLimit,
    Requirement,
    Target,
    deciding_check,
    load_of,
)
from cad.briefs.origins import quoted
from cad.briefs.store import ProposalState, Status, TamperedBrief
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
DESCRIBED_DECIDES: Final = (
    "Decided by the {check} check, on a load case the agent described from fixed terms. "
    "The server wrote these words from those terms, and our team has not reviewed this load case"
)
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
        text, shown = self._shown(ref)
        names = plain_names(self._roots, shown.proposal.brief_id)
        rows = tuple(_row(r, text, names) for r in shown.proposal.requirements)
        return Section(title=TITLE, brief_id=shown.proposal.brief_id, context=text, rows=rows)

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

    def _shown(self, ref: ItemRef) -> tuple[str, ProposalState]:
        """The brief text and the proposal the ref names. Raises when either changed."""
        match = SLOT.fullmatch(ref.slot)
        if match is None:
            raise TamperedBrief(f"no proposal is stored at {ref.slot!r}")
        state = store.read_state(self._roots, match.group(1))
        shown = state.proposal(int(match.group(2)))
        if shown is None or shown.ref != ref:
            raise TamperedBrief(f"brief {state.brief.id} changed since the page opened")
        return state.brief.text, shown


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


def _row(requirement: Requirement, text: str, names: Mapping[str, str]) -> Row:
    source, quote = quoted(text, requirement.origin)
    return Row(
        headline=describe(requirement, names),
        quote=quote,
        source=source,
        decides=_decides(requirement.target),
        editable=_editable(requirement),
    )


def _decides(target: Target) -> str:
    if isinstance(target, MadeOf):
        return "Fixes the material that scoring uses"
    if isinstance(target, AgentLimit):
        return AGENT_DECIDES
    check = deciding_check(target)
    if check is None:
        return "No reviewed check: unverified"
    case = load_of(target)
    if case is not None and case.described:
        return DESCRIBED_DECIDES.format(check=check)
    if isinstance(target, MeasureLimit):
        words = BINDABLE[(target.check_id, target.measure)].words
        return f"Decided by the {check} check, which measures {words}"
    return f"Decided by the {check} check"

"""Proposed requirements as an item on the confirmation page: each brief's newest proposal."""

import re
from collections.abc import Sequence
from typing import Final

from cad.briefs import store
from cad.briefs.model import Kind, deciding_check, describe
from cad.briefs.store import Status, TamperedBrief
from cad.confirmations.answers import Edit, ItemKindName, ItemRef
from cad.confirmations.items import Row, Section
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId
from cad.records.roots import Roots

SLOT: Final = re.compile(r"([0-9a-f]{16})/proposal/([1-9][0-9]{0,3})")
NO_EDITS: Final = (
    "Editing a requirement on this page is not available yet. "
    "Decline and say what to change in the note."
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
        match = SLOT.fullmatch(ref.slot)
        if match is None:
            raise TamperedBrief(f"no proposal is stored at {ref.slot!r}")
        state = store.read_state(self._roots, match.group(1))
        shown = state.proposal(int(match.group(2)))
        if shown is None or shown.ref != ref:
            raise TamperedBrief(f"brief {state.brief.id} changed since the page opened")
        text = state.brief.text
        rows = tuple(
            Row(
                headline=describe(r),
                quote=text[r.origin.start : r.origin.end],
                decides=_decides(r.target.kind),
            )
            for r in shown.proposal.requirements
        )
        title = f"Requirements for your brief (proposal {shown.proposal.number})"
        return Section(title=title, context=text, rows=rows)

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> str | None:
        return NO_EDITS if edits else None


def _decides(kind: Kind) -> str:
    check = deciding_check(kind)
    return f"Decided by the {check} check" if check else "No reviewed check: unverified"

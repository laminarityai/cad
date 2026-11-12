"""The confirmation-page item that approves an agent-written check (ADR-0011).

A check waits on the page once a requirement of a brief in the project names it, beside the
requirements it decides. Approving it is the person's answer for the project: one answer per
check, and a declined check leaves its requirement unverified.
"""

import re
from collections.abc import Sequence
from typing import Final

from cad.agent_checks.store import StoredCheck, check_ref_slot, checks_of
from cad.briefs import store as briefs
from cad.briefs.model import AgentLimit
from cad.confirmations.answers import Edit, ItemKindName, ItemRef, read_ledger
from cad.confirmations.items import Changes, Refused, Row, Section
from cad.context_parts.model import Outcome
from cad.projects.membership import project_briefs
from cad.projects.model import ProjectId, TamperedProject, parse_project_id
from cad.records.roots import Roots

SLOT: Final = re.compile(r"([a-z]+-[0-9a-f]{16})/agent_check/([1-9][0-9]{0,3})")
TITLE: Final = "A check the agent wrote for your brief"
UNREVIEWED: Final = (
    "Our team has not reviewed this check. Approve it only if it tests what you meant: a "
    "variant's verdict on it is labelled as an agent-written check you approved."
)
NO_EDIT: Final = (
    "An agent-written check has no number to change here: change the limit on its requirement "
    "instead. If the check does not test what you meant, decline it and say why in the note."
)


class AgentChecks:
    def __init__(self, roots: Roots) -> None:
        self._roots = roots

    @property
    def name(self) -> ItemKindName:
        return "agent_check"

    def pending(self, project: ProjectId) -> tuple[ItemRef, ...]:
        return tuple(
            ref(project, one)
            for one in named(self._roots, project)
            if outcome(self._roots, project, one) == "waiting"
        )

    def section(self, ref: ItemRef) -> Section:
        stored = self._check_at(ref)
        check = stored.check
        brief = briefs.read_brief(self._roots, check.brief_id)
        example = check.example
        row = Row(
            headline=f"{check.title}: {check.measures}",
            quote=check.words,
            source=check.source,
            decides=(
                f"Computes {check.formula} and compares it with the limit you confirm. Its "
                f"source's own worked example, on {example.cited.url}, gives "
                f"{_amount(example.result.value, example.result.unit)}, and the formula gives "
                f"{_amount(example.computed, example.result.unit)}. {UNREVIEWED}"
            ),
        )
        return Section(title=TITLE, brief_id=brief.id, context=brief.text, rows=(row,))

    def edit(self, ref: ItemRef, edits: Sequence[Edit]) -> Refused | Changes:
        return Refused(NO_EDIT)

    def _check_at(self, ref: ItemRef) -> StoredCheck:
        match = SLOT.fullmatch(ref.slot)
        if match is None:
            raise TamperedProject(f"no agent-written check is stored at {ref.slot!r}")
        held = checks_of(self._roots.projects, parse_project_id(match.group(1)))
        number = int(match.group(2))
        if not 1 <= number <= len(held) or held[number - 1].sha256 != ref.sha256:
            raise TamperedProject(f"agent-written check {ref.slot} changed since the page opened")
        return held[number - 1]


def ref(project: ProjectId, stored: StoredCheck) -> ItemRef:
    return ItemRef(
        kind="agent_check", slot=check_ref_slot(project, stored.number), sha256=stored.sha256
    )


def named(roots: Roots, project: ProjectId) -> tuple[StoredCheck, ...]:
    """The project's checks that a requirement names, in the newest proposal or the confirmed
    set of one of its briefs."""
    wanted: set[str] = set()
    for brief_id in project_briefs(roots, project):
        latest = briefs.read_state(roots, brief_id).latest
        confirmed = briefs.confirmed_requirements(roots, brief_id)
        for held in (
            () if latest is None else latest.requirements,
            () if confirmed is None else confirmed.requirements,
        ):
            wanted.update(
                one.target.check_sha256 for one in held if isinstance(one.target, AgentLimit)
            )
    return tuple(one for one in checks_of(roots.projects, project) if one.sha256 in wanted)


def outcome(roots: Roots, project: ProjectId, stored: StoredCheck) -> Outcome:
    found = read_ledger(roots.projects, project).of(ref(project, stored))
    return "waiting" if found is None else found.item.verdict


def note(roots: Roots, project: ProjectId, stored: StoredCheck) -> str:
    found = read_ledger(roots.projects, project).of(ref(project, stored))
    return found.page.note if found is not None and found.item.verdict == "declined" else ""


def _amount(value: float, unit: str) -> str:
    """A number with its unit, and a ratio with none."""
    return f"{value:g}" if unit == "1" else f"{value:g} {unit}"

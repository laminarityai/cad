"""The result rule for described load cases (ADR-0007, amendment of 2026-11-11).

The agent combines a described load case from the closed list of terms, and the server writes
its words. It may do that while it has seen no stress result of the brief, so it never picks the
terms knowing which one a result favours. Once a `fea` result exists, the described cases the
brief holds are frozen: the force may change, because it is the person's number, and nothing
else may.
"""

from collections.abc import Callable, Sequence

from cad.briefs.model import Target, load_of
from cad.briefs.store import BadProposal, BriefState, Status
from cad.loads.model import UnitCaseKey

USE_A_REVIEWED_PHRASE = (
    "Describe this load with a reviewed phrase instead: a support of holes, largest_flat or "
    "flat_end, a load of far_end or on_holes, and a direction of along, across or any. If no "
    "phrase says it, propose the requirement as unchecked and say that it was not checked"
)


def described_cases(targets: Sequence[Target]) -> dict[UnitCaseKey, int]:
    """The unit case of each described load case among `targets`, with the first index that
    carries it."""
    found: dict[UnitCaseKey, int] = {}
    for index, target in enumerate(targets):
        case = load_of(target)
        if case is not None and case.described:
            found.setdefault(case.unit_case, index)
    return found


def check_proposed(
    state: BriefState, targets: Sequence[Target], stressed: Callable[[], bool]
) -> None:
    """Raises BadProposal when `stressed()` and `targets` hold a described load case that no
    earlier proposal carried, or leave out one that the newest proposal carried and the person
    has not declined. `stressed` is asked only when a described load case is in play."""
    earlier: set[UnitCaseKey] = set()
    for proposal in state.proposals:
        earlier |= described_cases([one.target for one in proposal.requirements]).keys()
    proposed = described_cases(targets)
    if not (earlier or proposed) or not stressed():
        return
    for case, index in proposed.items():
        if case not in earlier:
            raise BadProposal(
                f"requirements[{index}] describes a load case that no earlier proposal of this "
                "brief carried, and a stress result of this brief already exists, so a new "
                f"description could be chosen for its result. {USE_A_REVIEWED_PHRASE}. The "
                "described case the brief holds may be proposed again with a new force"
            )
    newest = state.latest
    if newest is None or newest.status is Status.DECLINED:
        return
    kept = described_cases([one.target for one in newest.requirements])
    if lost := [case for case in kept if case not in proposed]:
        raise BadProposal(
            f"the proposal leaves out the described load case of requirement "
            f"{newest.requirements[kept[lost[0]]].id}, which proposal {newest.proposal.number} "
            "carried, and a stress result of this brief already exists. Propose it again, "
            "with a new force if the person gave one. Only a decline by the person lets a "
            "proposal leave it out"
        )


def refuse_assumed(targets: Sequence[Target], label: str = "assumptions") -> None:
    """A described load case is the person's to state with a force they gave, so it is never an
    assumption. Measuring under an assumed one would also give the brief a stress result."""
    if described := described_cases(targets):
        raise BadProposal(
            f"{label}[{min(described.values())}] is a described load case. Only a requirement "
            "the person stated may use one: propose it with the person's force, quoting their "
            "words"
        )

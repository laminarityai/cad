"""Read each variant, material and brief a session scored with through the server's own
`scorecard` read, after the session ends.

In build-first the agent scores before the person confirms, and Confirm judges the same stored
check results with no rebuild, so no card the agent was shown need hold the judged state. The
reading is that state: the operation the agent and the page call, over the session's own stores.
It builds, runs and waits for nothing, and it writes nothing.
"""

from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Final

from provenance import CardTrace, Unreadable
from pydantic import ValidationError
from trace_store import SHOWN

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.errors import Refused, Unavailable
from cad.operations.scorecards import ScorecardInput, ScoredBody, scorecard
from cad.operations.tenants import open_tenant
from cad.records.roots import Roots
from cad.scorecard.model import AgainstBrief, AwaitingConfirmation, Scorecard

LOCAL: Final = AccountId("local")
READ_AFTER: Final = "read after the session"


def read_after(stores: Path, shown: Sequence[str | CardTrace]) -> tuple[str | CardTrace, ...]:
    """The server's card for each variant, material and brief a card in `shown` was scored with,
    ordered by its last card there, or why the server refused it. `shown` is the cards the
    session got."""
    variants = stores / "variants"
    roots = Roots(briefs=stores / "briefs", projects=stores / "projects")
    tenant = open_tenant(LOCAL, roots, variants, stores / "geometry", None, Door(), ingest)
    readings: list[str | CardTrace] = []
    for asked in _scored(shown):
        try:
            card = scorecard(tenant, asked)
        except (Refused, Unavailable) as error:
            refused = Unreadable(f"the server's scorecard read refused it: {error}")
            readings.append(CardTrace(asked.variant_id, (refused,), ()))
            continue
        readings.append(card.model_dump_json(by_alias=True))
    return tuple(readings)


def _scored(shown: Sequence[str | CardTrace]) -> Iterator[ScorecardInput]:
    last: dict[ReadingKey, None] = {}
    for text in shown:
        if isinstance(text, CardTrace):
            continue
        try:
            key = reading_key(SHOWN.validate_json(text))
        except ValidationError:
            continue
        if key is None:
            continue
        last.pop(key, None)
        last[key] = None
    for variant_id, material_key, materials, brief_id in last:
        yield ScorecardInput(
            variant_id=variant_id,
            material_key=material_key,
            materials=tuple(ScoredBody(body=body, key=key) for body, key in materials) or None,
            brief_id=brief_id,
        )


type ReadingKey = tuple[str, str | None, tuple[tuple[str, str], ...], str]


def reading_key(card: Scorecard) -> ReadingKey | None:
    """The variant, material and brief the server reads a card's variant for, or None for a card
    scored with no brief."""
    if not isinstance(card.basis, AgainstBrief | AwaitingConfirmation):
        return None
    each = tuple((one.body, one.key) for one in card.materials)
    return (card.variant_id, card.material_key, each, card.basis.brief_id)

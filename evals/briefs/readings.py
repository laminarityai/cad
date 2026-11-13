"""Read each variant a session scored with a brief through the server's own `scorecard` read,
after the session ends.

In build-first the agent scores before the person confirms, and Confirm judges the same stored
check results with no rebuild, so no card the agent was shown need hold the judged state. The
reading is that state: the operation the agent and the page call, over the session's own stores.
It builds, runs and waits for nothing, and it writes nothing.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Final

from provenance import CardTrace, Unreadable
from trace_store import TracedStore

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.errors import Refused, Unavailable
from cad.operations.scorecards import ScorecardInput, scorecard
from cad.operations.tenants import open_tenant
from cad.records.roots import Roots

LOCAL: Final = AccountId("local")
READ_AFTER: Final = "read after the session"


def read_after(stores: Path, shown: TracedStore) -> tuple[str | CardTrace, ...]:
    """The server's card for each variant scored with a brief, ordered by its last card in the
    session, or why the server refused it."""
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


def _scored(shown: TracedStore) -> Iterator[ScorecardInput]:
    last: dict[tuple[str, str, str], None] = {}
    for one in shown.cards:
        if one.card is None or one.trace.brief_id is None:
            continue
        key = (one.card.variant_id, one.card.material_key, one.trace.brief_id)
        last.pop(key, None)
        last[key] = None
    for variant_id, material_key, brief_id in last:
        yield ScorecardInput(variant_id=variant_id, material_key=material_key, brief_id=brief_id)

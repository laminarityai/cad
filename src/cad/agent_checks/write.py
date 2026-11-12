"""Write one agent-written check: run every gate, then freeze the record (ADR-0011)."""

from collections.abc import Callable
from datetime import UTC, date, datetime

from cad.agent_checks import example, gates, store
from cad.agent_checks.model import AgentCheck, CheckDraft
from cad.agent_checks.store import CheckRefused, StoredCheck
from cad.briefs import store as briefs
from cad.records.roots import Roots
from cad.research.pdf import fetch_source
from cad.research.submit import Fetch


def write_check(
    roots: Roots,
    brief_id: str,
    requirement_id: str,
    draft: CheckDraft,
    *,
    fetcher: Fetch | None = None,
    today: Callable[[], date] = date.today,
) -> StoredCheck:
    """Raises CheckRefused, naming the first gate that refused, when nothing was stored."""
    project = briefs.read_brief(roots, brief_id).project
    written_for = _passed(gates.written_for(roots, brief_id, requirement_id))
    _refuse(gates.blind(roots, project, brief_id))
    _refuse(store.over_the_limit(store.checks_of(roots.projects, project), brief_id))
    shaped = _passed(gates.form(draft))
    _refuse(gates.units(draft, shaped))
    pages = example.Pages(fetcher or fetch_source, today)
    cited = _passed(example.sources(draft, pages))
    worked = _passed(example.worked_example(draft, shaped, cited, pages))
    check = AgentCheck(
        project=project,
        brief_id=brief_id,
        requirement_id=requirement_id,
        source=written_for.source,
        words=written_for.words,
        title=draft.title,
        measures=draft.measures,
        geometry=draft.geometry,
        probe=draft.probe,
        formula=draft.formula,
        inputs=shaped.bound,
        sources=cited,
        comparator=draft.limit.comparator,
        unit=draft.limit.unit,
        limit_source=draft.limit.source,
        example=worked,
        written_at=datetime.now(UTC),
    )
    return store.freeze(roots.projects, check, lambda: gates.blind(roots, project, brief_id))


def _passed[T](found: T | str) -> T:
    if isinstance(found, str):
        raise CheckRefused(f"{found}. Nothing was stored.")
    return found


def _refuse(reason: str | None) -> None:
    if reason is not None:
        raise CheckRefused(f"{reason}. Nothing was stored.")

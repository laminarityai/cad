from collections.abc import Iterable, Sequence
from typing import Final

from cad.checks.result import CheckResult, ReadMissing
from cad.frozen import Frozen
from cad.research.overlay import Dropped
from cad.scorecard.model import PendingCheck
from cad.tables.fields import FIELDS, Field
from cad.tables.materials import MaterialsTable, Unknown, row_or_blank

SUBMIT: Final = "submit_research"
RESCORE: Final = "Then call score_variant again."


class ResearchRequest(Frozen):
    """`low` and `high` bound the value in `unit` that the server accepts; when `exclusive`, the
    bounds themselves are refused. `problems` says why an earlier answer for the same field gave
    no value."""

    brief_id: str | None
    key: str
    field: Field
    unit: str
    low: float
    high: float
    exclusive: bool
    instruction: str
    problems: tuple[str, ...] = ()


def request_for(
    brief_id: str | None,
    key: str,
    field: Field,
    problems: Sequence[str] = (),
    then: str = RESCORE,
) -> ResearchRequest:
    spec = FIELDS[field]
    if brief_id is None:
        first = (
            "Score the variant again with a brief_id first: researched values are stored for "
            "the brief's project. Then "
        )
    else:
        first = ""
    instruction = (
        f"{first}research {field} for {key}: find a public https page that states the "
        f"{spec.label} of this material, and call {SUBMIT} with brief_id, key {key!r}, field "
        f"{field!r}, the value and its unit ({spec.unit_hint}) as the page writes them, the "
        "page's URL, and the quote you read the value from, copied from the "
        "page. The server fetches the page, checks that the quote is on it and that the value "
        "is written in the quote, cites the page, and labels the value researched. A source for "
        "a near material, such as plain PLA for a PLA blend, is allowed. The server accepts "
        f"{spec.accepts}. {then}"
    )
    return ResearchRequest(
        brief_id=brief_id,
        key=key,
        field=field,
        unit=spec.canonical_unit,
        low=spec.low,
        high=spec.high,
        exclusive=spec.exclusive,
        instruction=instruction,
        problems=tuple(problems),
    )


def requests_on(
    results: Iterable[CheckResult | PendingCheck],
    material_key: str,
    table: MaterialsTable,
    brief_id: str | None,
    dropped: Sequence[Dropped] = (),
) -> tuple[ResearchRequest, ...]:
    material = row_or_blank(table.materials, material_key)
    if material is None:
        return ()
    problems: dict[str, list[str]] = {}
    for one in dropped:
        if one.record.key == material_key:
            problems.setdefault(one.record.field, []).extend(one.problems)
    wanted: dict[Field, None] = {}
    for result in results:
        for read in result.reads:
            field = _field(read.field) if isinstance(read, ReadMissing) else None
            if field is not None and isinstance(material.value(field), Unknown):
                wanted[field] = None
    return tuple(
        request_for(brief_id, material_key, field, problems.get(field, ())) for field in wanted
    )


def requests_before_scoring(
    table: MaterialsTable, key: str, fields: Iterable[str], brief_id: str, then: str
) -> tuple[ResearchRequest, ...]:
    material = row_or_blank(table.materials, key)
    if material is None:
        return ()
    wanted: dict[Field, None] = {
        field: None for name in fields if (field := _field(name)) is not None
    }
    return tuple(
        request_for(brief_id, key, field, then=then)
        for field in wanted
        if isinstance(material.value(field), Unknown)
    )


def _field(name: str) -> Field | None:
    return next((field for field in FIELDS if field == name), None)

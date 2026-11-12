"""G3, the worked example, and the source constants a check reads (ADR-0011, ADR-0009).

The server fetches each page with the research rules, finds the quote on it, finds each number
written in its quote, and evaluates the formula on the example's inputs. The answer must match
the example's written result to half a unit in its last digit, or 1%, whichever is larger. What
it takes on trust is what ADR-0009 trusts: the unit of each number, which number is which input,
and that the page is an authority.
"""

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal

import pint

from cad.agent_checks.formula import evaluate
from cad.agent_checks.gates import Shaped
from cad.agent_checks.model import (
    UNITS,
    CheckDraft,
    Cited,
    Example,
    NamedValue,
    SourceInput,
    SourceValue,
    Written,
)
from cad.research.fetch import FetchFailed, Page, PdfText
from cad.research.submit import Fetch
from cad.tables.materials import UNITS as PINT
from cad.tables.quote import on_page, written_as_one_number

RELATIVE: float = 0.01


class Pages:
    """Each URL fetched once per call, so a source and the example may share a page."""

    def __init__(self, fetcher: Fetch, today: Callable[[], date]) -> None:
        self._fetcher = fetcher
        self._today = today
        self._fetched: dict[str, Page | PdfText | FetchFailed] = {}

    def cite(self, url: str, quote: str, what: str) -> Cited | str:
        fetched = self._fetched.get(url) or self._fetched.setdefault(url, self._fetcher(url))
        if isinstance(fetched, FetchFailed):
            return f"{what}: {fetched.reason}"
        pages = (fetched.text,) if isinstance(fetched, Page) else fetched.pages
        found = next((n for n, text in enumerate(pages, start=1) if on_page(quote, text)), None)
        if found is None:
            return (
                f"{what}: the quote does not appear on {fetched.url} as the server fetched it; "
                "copy its words and numbers in the page's order"
            )
        return Cited(
            url=fetched.url,
            title=fetched.title,
            sha256=fetched.sha256,
            retrieved=self._today(),
            page=found if isinstance(fetched, PdfText) else None,
        )


def quantity(written: Written | SourceValue | NamedValue) -> pint.Quantity:
    return PINT.Quantity(written.value, UNITS[written.unit])


def sources(draft: CheckDraft, pages: Pages) -> tuple[SourceValue, ...] | str:
    found: list[SourceValue] = []
    for one in draft.sources:
        what = f"source {one.name}"
        if not written_as_one_number(Decimal(repr(one.value)), one.quote):
            return f"{what}: {one.value:g} is not written in its quote as one number"
        cited = pages.cite(one.url, one.quote, what)
        if isinstance(cited, str):
            return cited
        found.append(
            SourceValue(name=one.name, value=one.value, unit=one.unit, quote=one.quote, cited=cited)
        )
    return tuple(found)


def worked_example(
    draft: CheckDraft, shaped: Shaped, cited_sources: tuple[SourceValue, ...], pages: Pages
) -> Example | str:
    given = draft.example
    for name, one in [*given.inputs.items(), ("the result", given.result)]:
        if not written_as_one_number(Decimal(repr(one.value)), given.quote):
            return f"the example's {name}, {one.value:g}, is not written in its quote as one number"
    cited = pages.cite(given.url, given.quote, "the example")
    if isinstance(cited, str):
        return cited
    held: Mapping[str, SourceValue] = {one.name: one for one in cited_sources}
    values = {
        one.name: quantity(held[one.binding.name])
        if isinstance(one.binding, SourceInput)
        else quantity(given.inputs[one.name])
        for one in shaped.bound
    }
    value = evaluate(shaped.formula, values)
    if isinstance(value, str):
        return f"on the example's inputs, {value}"
    computed = float(value.to(UNITS[given.result.unit]).magnitude)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    if abs(computed - given.result.value) > tolerance(given.result.value) * (1 + 1e-9):
        return (
            f"on the example's inputs the formula gives {computed:.6g} {given.result.unit}, but "
            f"the example writes {given.result.value:g} {given.result.unit}"
        )
    return Example(
        quote=given.quote,
        cited=cited,
        inputs=tuple(
            NamedValue(name=name, value=one.value, unit=one.unit)
            for name, one in given.inputs.items()
        ),
        result=given.result,
        computed=computed,
    )


def tolerance(written: float) -> float:
    """Half a unit in the last digit written, or 1%, whichever is larger."""
    exponent = 0 if written.is_integer() else Decimal(repr(written)).as_tuple().exponent
    last = 0.5 * 10.0**exponent if isinstance(exponent, int) else 0.0
    return max(last, RELATIVE * abs(written))

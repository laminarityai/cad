"""Whether a quote's conditions leave unclear which one the value applies to.

A quote reads with at most one temperature, one pressure and one humidity. Two of one kind
refuse, and the refusal says whether they agree within rounding, as 23 °C and 296 K do, or
differ.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from cad.sources.fields import FieldSpec
from cad.sources.refusal import Reason, Refusal
from cad.sources.scan import Unclear, read_number
from cad.sources.tokens import Token

# unit: (what it measures, offset, factor). (written + offset) * factor is in K, Pa or % RH.
_UNITS: Final[dict[str, tuple[str, Decimal, Decimal]]] = {
    "C": ("temperature", Decimal("273.15"), Decimal(1)),
    "F": ("temperature", Decimal("459.67"), Decimal(5) / 9),
    "K": ("temperature", Decimal(0), Decimal(1)),
    "Pa": ("pressure", Decimal(0), Decimal(1)),
    "kPa": ("pressure", Decimal(0), Decimal(1000)),
    "MPa": ("pressure", Decimal(0), Decimal(1000000)),
    "bar": ("pressure", Decimal(0), Decimal(100000)),
    "atm": ("pressure", Decimal(0), Decimal(101325)),
    "psi": ("pressure", Decimal(0), Decimal("6894.757")),
    "%RH": ("humidity", Decimal(0), Decimal(1)),
}
_WRITTEN: Final = re.compile(r"(-?)([\d.,]+)(.+)", re.ASCII)


@dataclass(frozen=True, slots=True)
class _Condition:
    token: Token
    kind: str
    written: str
    amount: Decimal | None
    half_step: Decimal


def several_conditions(found: list[Token], spec: FieldSpec) -> Refusal | None:
    seen: dict[str, _Condition] = {}
    for token in found:
        if token.kind != "condition":
            continue
        second = _condition(token)
        first = seen.setdefault(second.kind, second)
        if first.written == second.written:
            continue
        shown = f"{first.token.text!r} and {second.token.text!r}"
        if first.amount is None or second.amount is None:
            detail = f"the quote gives two {first.kind}s, {shown}, so it is unclear which one"
        elif abs(first.amount - second.amount) <= max(first.half_step, second.half_step):
            return Refusal(
                Reason.SEVERAL_CONDITIONS,
                f"the quote states the {first.kind} twice, as {shown}, which agree within "
                f"rounding; this reader reads a quote with one {first.kind}",
                f"a quote that states the {first.kind} once",
            )
        else:
            detail = (
                f"the quote gives two different {first.kind}s, {shown}, so it is unclear which one"
            )
        return Refusal(
            Reason.SEVERAL_CONDITIONS,
            f"{detail} the {spec.label} applies to",
            f"a quote with the {spec.label} at one {first.kind}",
        )
    return None


def _condition(token: Token) -> _Condition:
    """A condition token's kind, its text without "at", spaces or "°", and its amount."""
    written = re.sub(r"^(?i:at|@)|[ °]", "", token.text)
    match = _WRITTEN.fullmatch(written)
    assert match is not None, token.text
    sign, digits, unit = match.groups()
    kind, offset, factor = _UNITS[unit]
    number = read_number(digits)
    if isinstance(number, Unclear):
        return _Condition(token, kind, written, None, Decimal(0))
    exponent = number.as_tuple().exponent
    assert isinstance(exponent, int)
    amount = ((-number if sign else number) + offset) * factor
    return _Condition(token, kind, written, amount, Decimal(5).scaleb(exponent - 1) * factor)

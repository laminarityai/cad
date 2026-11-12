"""What an agent-written check is (ADR-0011): the draft the agent sends to `write_check`, and the
record the server freezes when every gate passes. A record is never edited. Its sha256 is its
identity, and a requirement names it by that sha256.
"""

import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Final, Literal, get_args

from pydantic import Field, PositiveInt

from cad.checks.result import Comparator
from cad.frozen import Frozen
from cad.tables.fields import Field as MaterialField

NAME: Final = re.compile(r"[a-z][a-z0-9_]{0,31}")
MAX_CHECKS_PER_BRIEF: Final = 4
MAX_CODE_CHARS: Final = 16 * 1024
MAX_FORMULA_CHARS: Final = 300
MAX_INPUTS: Final = 8
MAX_SOURCES: Final = 4
MAX_QUOTE_CHARS: Final = 1000
# The units a check states a number in, each with the pint name it means. Spelled as the
# geometry harness spells them, so one table serves the code, the pages and the limit.
UNITS: Final[Mapping[str, str]] = {
    "1": "dimensionless",
    "%": "percent",
    "mm": "mm",
    "cm": "cm",
    "m": "m",
    "in": "inch",
    "mm^2": "mm**2",
    "mm^3": "mm**3",
    "mm^4": "mm**4",
    "deg": "degree",
    "rad": "radian",
    "N": "newton",
    "kN": "kilonewton",
    "lbf": "lbf",
    "MPa": "MPa",
    "GPa": "GPa",
    "psi": "psi",
    "ksi": "ksi",
    "g": "g",
    "kg": "kg",
    "g/cm^3": "g/cm**3",
}
MATERIAL_FIELDS: Final[frozenset[str]] = frozenset(get_args(MaterialField.__value__))

type Name = Annotated[str, Field(pattern=f"^{NAME.pattern}$")]
type Unit = Annotated[str, Field(min_length=1, max_length=8)]
type Url = Annotated[str, Field(min_length=1, max_length=2000)]
type Quote = Annotated[str, Field(min_length=1, max_length=MAX_QUOTE_CHARS)]
type Number = Annotated[float, Field(allow_inf_nan=False)]


class Written(Frozen):
    """A number as a page or the person writes it, with its unit from `UNITS`."""

    value: Number
    unit: Unit


class SourceDraft(Frozen):
    name: Name
    value: Number
    unit: Unit
    url: Url
    quote: Quote


class ExampleDraft(Frozen):
    url: Url
    quote: Quote
    inputs: Annotated[dict[Name, Written], Field(max_length=MAX_INPUTS)]
    result: Written


class LimitDraft(Frozen):
    comparator: Comparator
    unit: Unit
    source: Name | None = None


class CheckDraft(Frozen):
    """The agent's check. `inputs` binds each name the formula reads to one of
    `geometry:<name>`, `team:<check>:<measure>`, `material:<field>` or `source:<name>`."""

    title: Annotated[str, Field(min_length=1, max_length=80)]
    measures: Annotated[str, Field(min_length=1, max_length=500)]
    geometry: Annotated[str, Field(min_length=1, max_length=MAX_CODE_CHARS)] | None = None
    probe: Annotated[str, Field(min_length=1, max_length=MAX_CODE_CHARS)] | None = None
    formula: Annotated[str, Field(min_length=1, max_length=MAX_FORMULA_CHARS)]
    inputs: Annotated[dict[Name, str], Field(min_length=1, max_length=MAX_INPUTS)]
    sources: Annotated[tuple[SourceDraft, ...], Field(max_length=MAX_SOURCES)] = ()
    limit: LimitDraft
    example: ExampleDraft


class GeometryInput(Frozen):
    kind: Literal["geometry"] = "geometry"
    name: Name


class TeamInput(Frozen):
    kind: Literal["team"] = "team"
    check_id: str
    measure: str


class MaterialInput(Frozen):
    kind: Literal["material"] = "material"
    field: MaterialField


class SourceInput(Frozen):
    kind: Literal["source"] = "source"
    name: Name


type Binding = Annotated[
    GeometryInput | TeamInput | MaterialInput | SourceInput, Field(discriminator="kind")
]


def parse_binding(raw: str) -> Binding | str:
    """The binding `raw` names, or why it names none. A team measure may hold a colon, as in
    `team:holes:hole_diameter:0`, so only the first two colons split."""
    kind, _, rest = raw.partition(":")
    match kind:
        case "geometry" if NAME.fullmatch(rest):
            return GeometryInput(name=rest)
        case "team" if ":" in rest:
            check_id, _, measure = rest.partition(":")
            return TeamInput(check_id=check_id, measure=measure)
        case "material" if rest in MATERIAL_FIELDS:
            return MaterialInput.model_validate({"field": rest})
        case "source" if NAME.fullmatch(rest):
            return SourceInput(name=rest)
        case _:
            fields = ", ".join(sorted(MATERIAL_FIELDS))
            return (
                f"binding {raw!r} is not geometry:<name>, team:<check>:<measure>, "
                f"material:<field> with a field of {fields}, or source:<name>"
            )


class Cited(Frozen):
    """A page the server fetched and found a quote on, as research cites one (ADR-0009)."""

    url: str
    title: str
    sha256: str
    retrieved: date
    page: PositiveInt | None = Field(default=None, exclude_if=lambda one: one is None)


class Bound(Frozen):
    name: Name
    binding: Binding


class SourceValue(Frozen):
    name: Name
    value: float
    unit: str
    quote: str
    cited: Cited


class NamedValue(Frozen):
    name: Name
    value: float
    unit: str


class Example(Frozen):
    """The source's own worked example, and what the formula gave on its inputs."""

    quote: str
    cited: Cited
    inputs: tuple[NamedValue, ...]
    result: Written
    computed: float


class AgentCheck(Frozen):
    """A frozen agent-written check. `requirement_id` and `words` name the stated requirement it
    was written for, and `source` says where those words are."""

    project: str
    brief_id: str
    requirement_id: str
    source: str
    words: str
    title: str
    measures: str
    geometry: str | None
    probe: str | None
    formula: str
    inputs: tuple[Bound, ...]
    sources: tuple[SourceValue, ...]
    comparator: Comparator
    unit: str
    limit_source: Name | None
    example: Example
    written_at: datetime

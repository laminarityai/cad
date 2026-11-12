"""The tolerances table: the tolerance classes a person may pick for a plain hole, by exact key.

`tables/tolerances.yaml` is read by exact key (`H7`, `ISO 2768-m`) and by the size range that holds
a hole's diameter, and by nothing else. No agent writes a row or supplies a value from it. A class
has one of two shapes:

- `above`, the hole classes H7, H8, H9 and H11 of ISO 286-1: from the nominal size up to the
  nominal size plus the limit;
- `symmetric`, the general tolerances of ISO 2768-1: the nominal size plus or minus the limit.

Each row holds the limit the source prints for a size range, in the class's unit. The sources are
cited by `cad.tables.datasheet_text`, which checks offline that each quote is on the stored page
and writes every number of its row.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, cast

import yaml
from pydantic import Field, ValidationError

from cad.frozen import Frozen
from cad.tables.materials import InvalidTable

TABLE_PATH = Path(__file__).resolve().parents[3] / "tables" / "tolerances.yaml"
CLASS_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .-]*")
MAX_CLASS_CHARS = 16
MICROMETRES_PER_MM = 1000

type Millimetres = Annotated[float, Field(ge=0, allow_inf_nan=False)]
type Limit = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Shape(StrEnum):
    ABOVE = "above"
    SYMMETRIC = "symmetric"


class Unit(StrEnum):
    MICROMETRE = "um"
    MILLIMETRE = "mm"


class Origin(Frozen):
    url: str
    title: str
    page: str
    retrieved: date
    standard: str


class Row(Frozen):
    """A size range, `over_mm` < size <= `up_to_mm` (from `over_mm` when `includes_over`, as the
    first range of ISO 2768-1 is), and the limit printed for it."""

    over_mm: Millimetres
    up_to_mm: Millimetres
    limit: Limit
    includes_over: bool = False
    quote: str = Field(min_length=1)
    range_quote: str | None = Field(default=None, min_length=1)

    def holds(self, size_mm: float) -> bool:
        above = self.over_mm <= size_mm if self.includes_over else self.over_mm < size_mm
        return above and size_mm <= self.up_to_mm


class ToleranceClass(Frozen):
    key: Annotated[str, Field(pattern=f"^{CLASS_PATTERN.pattern}$", max_length=MAX_CLASS_CHARS)]
    shape: Shape
    unit: Unit
    origin: Origin
    rows: tuple[Row, ...] = Field(min_length=1)

    @property
    def smallest_mm(self) -> float:
        return self.rows[0].over_mm

    @property
    def largest_mm(self) -> float:
        return self.rows[-1].up_to_mm

    def limit_mm(self, row: Row) -> float:
        return row.limit / MICROMETRES_PER_MM if self.unit is Unit.MICROMETRE else row.limit

    @property
    def covers(self) -> str:
        start = "from" if self.rows[0].includes_over else "over"
        return f"{start} {self.smallest_mm:g} mm up to {self.largest_mm:g} mm"


@dataclass(frozen=True, slots=True)
class Limits:
    """The diameters a hole of this class may have, inclusive, in mm."""

    low_mm: float
    high_mm: float


class UnknownClass(LookupError):
    pass


class OutsideClass(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TolerancesTable:
    version: str
    classes: Mapping[str, ToleranceClass]

    def get(self, key: str) -> ToleranceClass:
        found = self.classes.get(key)
        if found is None:
            raise UnknownClass(
                f"no tolerance class {key!r}; the classes are {', '.join(self.classes)}"
            )
        return found

    def limits(self, key: str, diameter_mm: float) -> Limits:
        """The limits at this nominal diameter, from the one row whose range holds it."""
        found = self.get(key)
        row = next((one for one in found.rows if one.holds(diameter_mm)), None)
        if row is None:
            raise OutsideClass(
                f"{key} covers sizes {found.covers}, and {diameter_mm:g} mm is outside that"
            )
        limit = found.limit_mm(row)
        if found.shape is Shape.ABOVE:
            return Limits(diameter_mm, diameter_mm + limit)
        return Limits(diameter_mm - limit, diameter_mm + limit)


def load_tolerances(path: Path = TABLE_PATH) -> TolerancesTable:
    return _parsed(path.read_bytes())


@lru_cache(maxsize=4)
def _parsed(data: bytes) -> TolerancesTable:
    document = cast(object, yaml.safe_load(data))
    raw = (
        cast(object, cast(dict[str, object], document).get("classes"))
        if isinstance(document, dict)
        else None
    )
    if not isinstance(raw, list):
        raise InvalidTable(["table: top level must be a mapping with a 'classes' list"])
    problems: list[str] = []
    classes: dict[str, ToleranceClass] = {}
    for index, item in enumerate(cast(list[object], raw)):
        try:
            one = ToleranceClass.model_validate(item)
        except ValidationError as error:
            problems.extend(f"class {index}: {line}" for line in _lines(error))
            continue
        if one.key in classes:
            problems.append(f"{one.key}: key appears twice")
        problems.extend(rule_problems(one))
        classes[one.key] = one
    if problems:
        raise InvalidTable(problems)
    return TolerancesTable(version=hashlib.sha256(data).hexdigest(), classes=classes)


def _lines(error: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, one['loc']))}: {one['msg']}" for one in error.errors()]


def rule_problems(one: ToleranceClass) -> list[str]:
    """What a class must satisfy for any shape: its ranges are in order and meet end to end, only
    the first may include its lower end, and the limit never shrinks as the size grows."""
    problems: list[str] = []
    for before, after in zip(one.rows, one.rows[1:], strict=False):
        if before.up_to_mm != after.over_mm or after.includes_over:
            problems.append(f"{one.key}: the range up to {before.up_to_mm:g} mm must meet the next")
        if after.limit < before.limit:
            problems.append(
                f"{one.key}: the limit at {after.up_to_mm:g} mm is below the one at"
                f" {before.up_to_mm:g} mm"
            )
    problems.extend(
        f"{one.key}: a range must end above where it starts, not {row.over_mm:g} to"
        f" {row.up_to_mm:g} mm"
        for row in one.rows
        if row.up_to_mm <= row.over_mm
    )
    return problems

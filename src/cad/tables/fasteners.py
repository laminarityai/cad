"""The fasteners table: the hole diameters a metric size takes, by exact key.

`tables/fasteners.yaml` is read by exact key (`M5`) and by nothing else. No agent writes a row or
supplies a value from it. A row holds two cited facts about one size:

- `clearance`, the diameters ISO 273 gives a bolt to pass through: close, medium and coarse series;
- `tapped`, the minor diameter of an internal thread, smallest to its 6H largest, and the tap drill
  that cuts it.

Every number is in mm. Each fact carries its source, and `cad.tables.datasheet_text` checks offline
that the source's quote is on the stored page and writes every number.
"""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, cast

import yaml
from pydantic import Field, ValidationError

from cad.frozen import Frozen
from cad.tables.materials import InvalidTable, Source

TABLE_PATH = Path(__file__).resolve().parents[3] / "tables" / "fasteners.yaml"
SIZE_PATTERN = re.compile(r"M[1-9][0-9]*(?:\.[0-9]+)?")
MAX_SIZE_CHARS = 8

type Millimetres = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ClearanceSeries(StrEnum):
    """The series of ISO 273 clearance holes: close (fine), medium and coarse."""

    CLOSE = "close"
    MEDIUM = "medium"
    COARSE = "coarse"


class Clearance(Frozen):
    close_mm: Millimetres
    medium_mm: Millimetres
    coarse_mm: Millimetres
    source: Source

    def diameter_mm(self, series: ClearanceSeries) -> float:
        match series:
            case ClearanceSeries.CLOSE:
                return self.close_mm
            case ClearanceSeries.MEDIUM:
                return self.medium_mm
            case ClearanceSeries.COARSE:
                return self.coarse_mm


class Tapped(Frozen):
    minor_min_mm: Millimetres
    minor_max_mm: Millimetres
    tap_drill_mm: Millimetres
    source: Source


class Fastener(Frozen):
    key: Annotated[str, Field(pattern=f"^{SIZE_PATTERN.pattern}$", max_length=MAX_SIZE_CHARS)]
    clearance: Clearance
    tapped: Tapped

    @property
    def nominal_mm(self) -> float:
        return float(self.key[1:])


class UnknownFastener(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class FastenersTable:
    version: str
    rows: Mapping[str, Fastener]

    def get(self, key: str) -> Fastener:
        row = self.rows.get(key)
        if row is None:
            raise UnknownFastener(f"no fastener {key!r}; the sizes are {', '.join(self.rows)}")
        return row


def load_fasteners(path: Path = TABLE_PATH) -> FastenersTable:
    return _parsed(path.read_bytes())


@lru_cache(maxsize=4)
def _parsed(data: bytes) -> FastenersTable:
    document = cast(object, yaml.safe_load(data))
    raw = (
        cast(object, cast(dict[str, object], document).get("fasteners"))
        if isinstance(document, dict)
        else None
    )
    if not isinstance(raw, list):
        raise InvalidTable(["table: top level must be a mapping with a 'fasteners' list"])
    problems: list[str] = []
    rows: dict[str, Fastener] = {}
    for index, item in enumerate(cast(list[object], raw)):
        try:
            row = Fastener.model_validate(item)
        except ValidationError as error:
            problems.extend(f"row {index}: {line}" for line in _lines(error))
            continue
        if row.key in rows:
            problems.append(f"{row.key}: key appears twice")
        problems.extend(rule_problems(row))
        rows[row.key] = row
    if problems:
        raise InvalidTable(problems)
    return FastenersTable(version=hashlib.sha256(data).hexdigest(), rows=rows)


def _lines(error: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, one['loc']))}: {one['msg']}" for one in error.errors()]


def rule_problems(row: Fastener) -> list[str]:
    """What a row must satisfy for any thread: a clearance hole is wider than the bolt and grows
    with the series, an internal thread's minor diameter is below the bolt's, and the tap drill
    lies inside the minor diameter's tolerance."""
    problems: list[str] = []
    clearance, tapped = row.clearance, row.tapped
    if not row.nominal_mm < clearance.close_mm <= clearance.medium_mm <= clearance.coarse_mm:
        problems.append(
            f"{row.key}: clearance must satisfy size < close <= medium <= coarse, not"
            f" {clearance.close_mm:g}, {clearance.medium_mm:g}, {clearance.coarse_mm:g} mm"
        )
    if not 0 < tapped.minor_min_mm <= tapped.tap_drill_mm <= tapped.minor_max_mm < row.nominal_mm:
        problems.append(
            f"{row.key}: tapped must satisfy minor_min <= tap_drill <= minor_max < size, not"
            f" {tapped.minor_min_mm:g}, {tapped.tap_drill_mm:g}, {tapped.minor_max_mm:g} mm"
        )
    return problems

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

import pint
import yaml

UNITS = pint.UnitRegistry()
TABLE_PATH = Path(__file__).resolve().parents[3] / "tables" / "materials.yaml"
KEY_PATTERN = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
PROJECT_PREFIX = "project-"
DENSITY_RANGE_KG_PER_M3 = (500.0, 20000.0)
ELASTIC_MODULUS_RANGE_GPA = (0.01, 500.0)
MAX_YIELD_STRAIN = 0.1
FIELD_UNITS = {
    "density": "kg/m^3",
    "yield_strength": "MPa",
    "tensile_strength": "MPa",
    "elastic_modulus": "MPa",
    "poisson_ratio": "dimensionless",
}
SOURCE_TEXT_FIELDS = ("url", "title", "page", "quote")

type Raw = Mapping[object, object]


@dataclass(frozen=True, slots=True)
class Source:
    url: str
    title: str
    page: str
    retrieved: date
    standard: str | None
    quote: str


@dataclass(frozen=True, slots=True)
class FromTable:
    pass


@dataclass(frozen=True, slots=True)
class FromResearch:
    sha256: str
    record: int


type Basis = FromTable | FromResearch


@dataclass(frozen=True, slots=True)
class Known:
    quantity: pint.Quantity
    source: Source
    basis: Basis = FromTable()

    def magnitude_in(self, unit: str) -> float:
        return magnitude(self.quantity, unit)


@dataclass(frozen=True, slots=True)
class Unknown:
    pass


type Value = Known | Unknown


@dataclass(frozen=True, slots=True)
class Material:
    key: str
    name: str
    density: Value
    yield_strength: Value
    tensile_strength: Value
    elastic_modulus: Value
    poisson_ratio: Value

    def value(self, field: str) -> Value:
        if field not in FIELD_UNITS:
            raise KeyError(field)
        return cast(Value, getattr(self, field))


def row_or_blank(materials: Mapping[str, Material], key: str) -> Material | None:
    found = materials.get(key)
    if found is None and key.startswith(PROJECT_PREFIX):
        return Material(key, key, **dict.fromkeys(FIELD_UNITS, Unknown()))
    return found


class UnknownMaterial(LookupError):
    pass


class InvalidTable(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = tuple(problems)


@dataclass(frozen=True, slots=True)
class MaterialsTable:
    version: str
    materials: Mapping[str, Material]

    def get_material(self, key: str) -> Material:
        material = row_or_blank(self.materials, key)
        if material is None:
            known = ", ".join(sorted(self.materials))
            raise UnknownMaterial(f"no material with key {key!r}; keys are {known}")
        return material

    def name_of(self, key: str) -> str:
        """The name a person reads: the row's name, or the key without the prefix for a material
        only the project has, whose row is named by its key."""
        found = self.materials.get(key)
        return (key if found is None else found.name).removeprefix(PROJECT_PREFIX)

    def row_key(self, key: str) -> str:
        """The key of the row that holds the material `key` names: the git row when git has one,
        and the project's own row otherwise. The plain name never starts with the prefix, so no
        project row matches it, and an overlay gives the same key as git."""
        named = key
        while named.startswith(PROJECT_PREFIX):
            named = named.removeprefix(PROJECT_PREFIX)
        return named if named in self.materials else PROJECT_PREFIX + named


def load_materials(path: Path = TABLE_PATH) -> MaterialsTable:
    return _parsed(path.read_bytes())


@lru_cache(maxsize=4)
def _parsed(data: bytes) -> MaterialsTable:
    problems: list[str] = []
    materials: dict[str, Material] = {}
    for row in _rows(yaml.safe_load(data), problems):
        material = _parse_material(row, problems)
        if material is None:
            continue
        if material.key in materials:
            problems.append(f"{material.key}: key appears twice")
        materials[material.key] = material
    if problems:
        raise InvalidTable(problems)
    return MaterialsTable(version=hashlib.sha256(data).hexdigest(), materials=materials)


def magnitude(quantity: pint.Quantity, unit: str) -> float:
    # Pint's annotations leave conversions partly untyped, so the gap stays in this one place.
    return float(quantity.m_as(unit))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]


def _mapping(raw: object) -> Raw | None:
    return cast(Raw, raw) if isinstance(raw, dict) else None


def _rows(document: object, problems: list[str]) -> list[Raw]:
    top = _mapping(document)
    rows = top.get("materials") if top is not None else None
    if not isinstance(rows, list):
        problems.append("table: top level must be a mapping with a 'materials' list")
        return []
    parsed: list[Raw] = []
    for index, row in enumerate(cast(list[object], rows)):
        mapping = _mapping(row)
        if mapping is None:
            problems.append(f"row {index}: must be a mapping")
        else:
            parsed.append(mapping)
    return parsed


def _parse_material(row: Raw, problems: list[str]) -> Material | None:
    key = row.get("key")
    if not isinstance(key, str) or KEY_PATTERN.fullmatch(key) is None:
        problems.append(f"{key!r}: key must be lowercase words joined by '-'")
        return None
    if key.startswith(PROJECT_PREFIX):
        problems.append(f"{key}: the {PROJECT_PREFIX} prefix is kept for a project's own rows")
        return None
    name = row.get("name")
    if not isinstance(name, str) or not name:
        problems.append(f"{key}: name is missing")
        return None
    start = len(problems)
    values = {field: _parse_value(key, field, row.get(field), problems) for field in FIELD_UNITS}
    if len(problems) > start:
        return None
    material = Material(key, name, **values)
    problems.extend(rule_problems(material))
    return material


def _parse_value(key: str, field: str, raw: object, problems: list[str]) -> Value:
    if raw == "unknown":
        return Unknown()
    mapping = _mapping(raw)
    if mapping is None:
        problems.append(f"{key}: {field} must be 'unknown' or a mapping with value and source")
        return Unknown()
    if "source" not in mapping:
        problems.append(f"{key}: {field} has no source")
        return Unknown()
    text = mapping.get("value")
    if not isinstance(text, str):
        problems.append(f"{key}: {field} value must be a string with a unit, such as '1.24 g/cm^3'")
        return Unknown()
    try:
        quantity = UNITS.Quantity(text)
        magnitude(quantity, FIELD_UNITS[field])
    except pint.PintError as error:
        problems.append(f"{key}: {field} {text!r}: {error}")
        return Unknown()
    source = _parse_source(key, field, mapping.get("source"), problems)
    return Unknown() if source is None else Known(quantity, source)


def _parse_source(key: str, field: str, raw: object, problems: list[str]) -> Source | None:
    mapping = _mapping(raw)
    if mapping is None:
        problems.append(f"{key}: {field} source must be a mapping")
        return None
    text = {name: mapping.get(name) for name in SOURCE_TEXT_FIELDS}
    missing = [name for name, value in text.items() if not isinstance(value, str)]
    retrieved = mapping.get("retrieved")
    if not isinstance(retrieved, date):
        missing.append("retrieved")
    standard = mapping.get("standard")
    if "standard" not in mapping or not (standard is None or isinstance(standard, str)):
        missing.append("standard")
    if missing:
        problems.append(f"{key}: {field} source lacks {', '.join(missing)}")
        return None
    url, title, page, quote = (str(text[name]) for name in SOURCE_TEXT_FIELDS)
    return Source(url, title, page, cast(date, retrieved), cast(str | None, standard), quote)


def rule_problems(material: Material) -> list[str]:
    problems: list[str] = []
    density = material.density
    low, high = DENSITY_RANGE_KG_PER_M3
    if isinstance(density, Known) and not low <= density.magnitude_in("kg/m^3") <= high:
        problems.append(
            f"{material.key}: density {density.quantity:g~P} is outside the plausible range"
            f" {low:g} to {high:g} kg/m³"
        )
    yield_strength, tensile_strength = material.yield_strength, material.tensile_strength
    if (
        isinstance(yield_strength, Known)
        and isinstance(tensile_strength, Known)
        and yield_strength.magnitude_in("MPa") > tensile_strength.magnitude_in("MPa")
    ):
        problems.append(
            f"{material.key}: yield_strength {yield_strength.quantity:g~P} is above"
            f" tensile_strength {tensile_strength.quantity:g~P}"
        )
    modulus, poisson = material.elastic_modulus, material.poisson_ratio
    low, high = ELASTIC_MODULUS_RANGE_GPA
    if isinstance(modulus, Known) and not low <= modulus.magnitude_in("GPa") <= high:
        problems.append(
            f"{material.key}: elastic_modulus {modulus.quantity:g~P} is outside the plausible"
            f" range {low:g} to {high:g} GPa"
        )
    if isinstance(poisson, Known) and not 0 < poisson.magnitude_in("dimensionless") < 0.5:
        problems.append(
            f"{material.key}: poisson_ratio {poisson.magnitude_in('dimensionless'):g} is not"
            " above 0 and below 0.5"
        )
    if (
        isinstance(yield_strength, Known)
        and isinstance(modulus, Known)
        and yield_strength.magnitude_in("MPa") >= MAX_YIELD_STRAIN * modulus.magnitude_in("MPa")
    ):
        problems.append(
            f"{material.key}: yield_strength {yield_strength.quantity:g~P} is not below"
            f" {MAX_YIELD_STRAIN:g} of elastic_modulus {modulus.quantity:g~P}"
        )
    return problems

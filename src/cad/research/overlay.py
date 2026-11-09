import dataclasses
from dataclasses import dataclass
from pathlib import Path

from cad.projects.model import ProjectId
from cad.research.ledger import Ledger, ResearchedRecord, read_ledger
from cad.tables.materials import (
    UNITS,
    FromResearch,
    Known,
    Material,
    MaterialsTable,
    Source,
    row_or_blank,
    rule_problems,
)

PAGE = "quoted on the page the server fetched"


@dataclass(frozen=True, slots=True)
class Dropped:
    number: int
    record: ResearchedRecord
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectTable:
    table: MaterialsTable
    dropped: tuple[Dropped, ...] = ()
    problem: str | None = None


def project_table(git: MaterialsTable, projects: Path, project: ProjectId | None) -> ProjectTable:
    if project is None:
        return ProjectTable(git)
    return overlay(git, project, read_ledger(projects, project))


def overlay(git: MaterialsTable, project: ProjectId, ledger: Ledger) -> ProjectTable:
    materials = dict(git.materials)
    dropped: list[Dropped] = []
    for number, record in enumerate(ledger.records, start=1):
        filled = fill(materials, record, number)
        if isinstance(filled, Material):
            materials[record.key] = filled
        else:
            dropped.append(Dropped(number, record, tuple(filled)))
    count = len(ledger.records)
    version = f"{git.version}+{project}@r{count}" if count else git.version
    return ProjectTable(MaterialsTable(version, materials), tuple(dropped), ledger.problem)


def fill(
    materials: dict[str, Material], record: ResearchedRecord, number: int
) -> Material | list[str]:
    material = row_or_blank(materials, record.key)
    where = f"{record.key}: {record.field}"
    if material is None:
        return [f"{record.key}: no row in the materials table has this key"]
    current = material.value(record.field)
    if isinstance(current, Known):
        held = "researched" if isinstance(current.basis, FromResearch) else "cited"
        return [f"{where} already has a {held} value, which a researched value never replaces"]
    value = Known(
        UNITS.Quantity(record.magnitude, record.unit),
        Source(record.url, record.title, PAGE, record.retrieved, None, record.quote),
        FromResearch(record.sha256, number),
    )
    filled = dataclasses.replace(material, **{record.field: value})
    problems = rule_problems(filled)
    return problems or filled

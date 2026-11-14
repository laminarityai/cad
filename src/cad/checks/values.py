from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cad.checks.container.inputs import WIRE_UNITS, Input
from cad.checks.container.wire import ValueWire
from cad.checks.result import Read, ReadCited, ReadMissing, ReadResearched
from cad.tables.materials import (
    PROJECT_PREFIX,
    Basis,
    FromResearch,
    FromTable,
    Known,
    Material,
    MaterialsTable,
    Source,
    UnknownMaterial,
)


@dataclass(frozen=True, slots=True)
class TableRead:
    magnitude: float
    source: Source
    basis: Basis


type ReadKey = tuple[Input, str]


def values_of(
    key: str, table: MaterialsTable, taken: Sequence[Input], body: str
) -> tuple[dict[str, ValueWire], dict[ReadKey, TableRead]]:
    try:
        material = table.get_material(key)
    except UnknownMaterial as error:
        missing: ValueWire = {"kind": "unknown", "reason": str(error)}
        return dict.fromkeys(taken, missing), {}
    reads = {wanted: read for wanted in taken if (read := _read(material, wanted)) is not None}
    values: dict[str, ValueWire] = {
        wanted: _value(material, wanted, reads.get(wanted)) for wanted in taken
    }
    return values, {(wanted, body): read for wanted, read in reads.items()}


def _read(material: Material, wanted: Input) -> TableRead | None:
    known = material.value(wanted)
    if not isinstance(known, Known):
        return None
    magnitude = known.magnitude_in(WIRE_UNITS[wanted])
    return TableRead(magnitude, known.source, known.basis)


def _value(material: Material, wanted: Input, read: TableRead | None) -> ValueWire:
    if read is None and material.key.startswith(PROJECT_PREFIX):
        reason = f"{material.key} has no row in the materials table, and no {wanted} is researched"
        return {"kind": "unknown", "reason": reason}
    if read is None:
        reason = f"the materials table has no {wanted} for {material.key}: it says unknown"
        return {"kind": "unknown", "reason": reason}
    return {"kind": "known", "magnitude": read.magnitude}


def reads_from(
    takes: frozenset[Input],
    held: Mapping[ReadKey, TableRead],
    values: Mapping[str, ValueWire],
    body: str,
) -> tuple[Read, ...]:
    reads: list[Read] = []
    for wanted in sorted(takes):
        read = held.get((wanted, body))
        value = values.get(wanted)
        if read is not None:
            match read.basis:
                case FromResearch(sha256=sha256):
                    source = read.source
                    reads.append(
                        ReadResearched(
                            field=wanted,
                            url=source.url,
                            quote=source.quote,
                            sha256=sha256,
                            body=body,
                        )
                    )
                case FromTable(specimen=specimen):
                    reads.append(ReadCited(field=wanted, specimen=specimen, body=body))
        elif value is not None and value["kind"] == "unknown":
            reads.append(ReadMissing(field=wanted, reason=value["reason"], body=body))
    return tuple(reads)

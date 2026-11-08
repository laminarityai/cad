from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from cad.checks.container.wire import ValueWire


class Input(StrEnum):
    DENSITY = "density"
    YIELD_STRENGTH = "yield_strength"
    ELASTIC_MODULUS = "elastic_modulus"
    POISSON_RATIO = "poisson_ratio"


WIRE_UNITS: Final[Mapping[Input, str]] = {
    Input.DENSITY: "kg/mm^3",
    Input.YIELD_STRENGTH: "MPa",
    Input.ELASTIC_MODULUS: "MPa",
    Input.POISSON_RATIO: "dimensionless",
}


class Undeclared(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class Inputs:
    takes: frozenset[Input]
    values: Mapping[str, ValueWire]

    def value(self, wanted: Input) -> ValueWire:
        if wanted not in self.takes:
            raise Undeclared(f"{wanted} is not in the check's TAKES")
        return self.values.get(wanted, {"kind": "unknown", "reason": f"the host sent no {wanted}"})

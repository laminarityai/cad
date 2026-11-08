from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from cad.checks.container.wire import LoadCaseWire, ValueWire


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
    load_cases: tuple[LoadCaseWire, ...] = ()

    def value(self, wanted: Input) -> ValueWire:
        if wanted not in self.takes:
            raise Undeclared(f"{wanted} is not in the check's TAKES")
        return self.values.get(wanted, {"kind": "unknown", "reason": f"the host sent no {wanted}"})

    def load_case(self) -> LoadCaseWire:
        if len(self.load_cases) != 1:
            raise Undeclared(f"the host sent {len(self.load_cases)} load cases, not one")
        return self.load_cases[0]

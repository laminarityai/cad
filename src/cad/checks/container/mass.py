import math
from datetime import date

from cad.checks.container import closed_solid, interference
from cad.checks.container.check import (
    BodyPart,
    CheckModule,
    Quick,
    Subject,
    finding,
    measure,
    no_shape,
    required_pass,
)
from cad.checks.container.inputs import Input
from cad.checks.container.kernel import Kernel, Point, Shape, Unreadable
from cad.checks.container.wire import FindingWire, MeasuredWire, SourceLiteral

ID = "mass"
FORMULA = (
    "mass = volume * density, with volume and center of mass from surface integration over the "
    "shape and density from the materials table row for the given key; for a variant of named "
    "bodies, each body's volume, density and mass are volume:<body>, density:<body> and "
    "mass:<body>, from its own solids and its own material's row, mass is their sum and "
    "center_of_mass the mean of the bodies' centers weighted by mass, and while any body's "
    "density is unknown neither mass nor center_of_mass is measured; unknown, with no "
    "measured value, unless closed_solid and interference pass"
)
SOURCES: tuple[SourceLiteral, ...] = (
    {
        "url": "https://occt3d.com/dev/doc/refman/html/class_b_rep_g_prop.html",
        "title": "Open CASCADE Technology 8.0.1 Reference Manual: BRepGProp Class",
        "page": "BRepGProp::VolumeProperties",
        "retrieved": date(2026, 11, 6),
        "standard": None,
        "quote": "Consequently, the added mass corresponds to the volume of S.",
    },
)
MEASURES = {
    "volume": "mm^3",
    "center_of_mass": "mm",
    "density": "kg/mm^3",
    "mass": "kg",
}
TAKES = frozenset({Input.DENSITY})
READS = {"density": Input.DENSITY}
REQUIRES: tuple[CheckModule, ...] = (closed_solid, interference)
BUDGET = Quick()
ERROR_BOUNDS: dict[str, float] = {}


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    unmet = required_pass(subject, REQUIRES, "weigh")
    if unmet is not None:
        return unmet
    if subject.bodies:
        return _weighed(subject.kernel, subject.kernel.solids(shape), subject.bodies)
    props = subject.kernel.volume_props(shape)
    if not math.isfinite(props.volume):
        return finding("fail", "the volume is not a finite number")
    x, y, z = props.center
    measured = (
        measure("volume", props.volume, "mm^3"),
        measure("center_of_mass:x", x, "mm"),
        measure("center_of_mass:y", y, "mm"),
        measure("center_of_mass:z", z, "mm"),
    )
    if props.volume <= 0:
        return finding(
            "fail", f"the volume is {props.volume:g} mm^3; it must be above 0", *measured
        )
    density = subject.inputs.value(Input.DENSITY)
    if density["kind"] == "unknown":
        return finding("unknown", density["reason"], *measured)
    kg_per_mm3 = density["magnitude"]
    return finding(
        "pass",
        f"{props.volume:g} mm^3 at {kg_per_mm3:g} kg/mm^3",
        *measured,
        measure("density", kg_per_mm3, "kg/mm^3"),
        measure("mass", props.volume * kg_per_mm3, "kg"),
    )


def _weighed(
    kernel: Kernel, solids: tuple[Shape, ...], bodies: tuple[BodyPart, ...]
) -> FindingWire:
    each: list[MeasuredWire] = []
    weights: list[tuple[float, Point]] = []
    unknown: list[str] = []
    whole = 0.0
    for body in bodies:
        props = [kernel.volume_props(solids[index]) for index in body.solids]
        volume = sum(one.volume for one in props)
        if not (math.isfinite(volume) and volume > 0):
            return finding(
                "fail", f"the volume of {body.name} is {volume:g} mm^3; it must be above 0"
            )
        whole += volume
        each.append(measure(f"volume:{body.name}", volume, "mm^3"))
        density = body.inputs.value(Input.DENSITY)
        if density["kind"] == "unknown":
            unknown.append(f"{body.name}: {density['reason']}")
            continue
        mass = volume * density["magnitude"]
        each.append(measure(f"density:{body.name}", density["magnitude"], "kg/mm^3"))
        each.append(measure(f"mass:{body.name}", mass, "kg"))
        centre = _mean([(one.volume, one.center) for one in props])
        weights.append((mass, centre))
    if unknown:
        said = "; ".join(unknown)
        return finding(
            "unknown",
            f"no mass is measured while a density is unknown: {said}",
            measure("volume", whole, "mm^3"),
            *each,
        )
    total = sum(mass for mass, _ in weights)
    x, y, z = _mean(weights)
    return finding(
        "pass",
        f"{total:g} kg over {len(bodies)} bodies, each at its own material's density",
        measure("volume", whole, "mm^3"),
        measure("center_of_mass:x", x, "mm"),
        measure("center_of_mass:y", y, "mm"),
        measure("center_of_mass:z", z, "mm"),
        *each,
        measure("mass", total, "kg"),
    )


def _mean(weighted: list[tuple[float, Point]]) -> Point:
    total = sum(weight for weight, _ in weighted)
    x, y, z = (sum(weight * at[axis] for weight, at in weighted) / total for axis in range(3))
    return (x, y, z)

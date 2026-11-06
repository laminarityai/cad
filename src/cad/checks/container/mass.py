import math
from datetime import date

from cad.checks.container import closed_solid, interference
from cad.checks.container.check import CheckModule, Subject, finding, measure, no_shape
from cad.checks.container.kernel import Unreadable
from cad.checks.container.wire import FindingWire, SourceLiteral

ID = "mass"
FORMULA = (
    "mass = volume * density, with volume and center of mass from surface integration over the "
    "shape and density from the materials table row for the given key; unknown, with no "
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
REQUIRES: tuple[CheckModule, ...] = (closed_solid, interference)


def run(subject: Subject) -> FindingWire:
    shape = subject.shape
    if isinstance(shape, Unreadable):
        return no_shape(shape)
    for required in REQUIRES:
        found = required.run(subject)
        if found["verdict"] != "pass":
            return finding(
                "unknown",
                f"{required.ID} is {found['verdict']}, so there is no one solid to "
                f"weigh: {found['reason']}",
            )
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
    density = subject.density
    if density["kind"] == "unknown":
        return finding("unknown", density["reason"], *measured)
    kg_per_mm3 = density["kg_per_mm3"]
    return finding(
        "pass",
        f"{props.volume:g} mm^3 at {kg_per_mm3:g} kg/mm^3",
        *measured,
        measure("density", kg_per_mm3, "kg/mm^3"),
        measure("mass", props.volume * kg_per_mm3, "kg"),
    )

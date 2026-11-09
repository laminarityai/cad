from typing import Final

from cad.checks.container.kernel import Kernel, Shape

MAX_TOLERANCE_MM: Final = 1e-3


def unmeasurable(kernel: Kernel, shape: Shape) -> str | None:
    """Why Common and DistShapeShape cannot be trusted on the shape, or None. The rules come from
    issue #92, except the volume rule: a reversed solid passes BRepCheck_Analyzer, and one nested
    in a good solid still leaves the total volume positive."""
    solids = kernel.solids(shape)
    if not solids:
        return "has no solid"
    outside = kernel.outside_solids(shape)
    if outside:
        return f"has {outside} shells, faces, edges or vertices outside any solid"
    invalid = [str(index) for index, solid in enumerate(solids) if not kernel.is_valid(solid)]
    if invalid:
        return f"has solids that BRepCheck_Analyzer calls invalid: {', '.join(invalid)}"
    volumes = (kernel.volume_props(solid).volume for solid in solids)
    inside_out = [str(index) for index, volume in enumerate(volumes) if not volume > 0]
    if inside_out:
        return (
            f"has solids with a volume of 0 or less, inside out or empty: {', '.join(inside_out)}"
        )
    tolerance = kernel.max_tolerance(shape)
    if tolerance > MAX_TOLERANCE_MM:
        return f"has a tolerance of {tolerance:g} mm, over the {MAX_TOLERANCE_MM:g} mm limit"
    return None

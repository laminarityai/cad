from typing import Final

from cad.checks.container.kernel import Kernel, Shape

MAX_TOLERANCE_MM: Final = 1e-3


def unmeasurable(kernel: Kernel, shape: Shape) -> str | None:
    """Why Common and DistShapeShape cannot be trusted on the shape, or None. Each rule comes from
    a case in issue #92 where one of them returned a wrong number."""
    solids = kernel.solids(shape)
    if not solids:
        return "has no solid"
    outside = kernel.outside_solids(shape)
    if outside:
        return f"has {outside} shells, faces, edges or vertices outside any solid"
    invalid = [str(index) for index, solid in enumerate(solids) if not kernel.is_valid(solid)]
    if invalid:
        return f"has solids that BRepCheck_Analyzer calls invalid: {', '.join(invalid)}"
    tolerance = kernel.max_tolerance(shape)
    if tolerance > MAX_TOLERANCE_MM:
        return f"has a tolerance of {tolerance:g} mm, over the {MAX_TOLERANCE_MM:g} mm limit"
    return None

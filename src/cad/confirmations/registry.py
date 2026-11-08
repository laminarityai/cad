from cad.confirmations.items import Kinds
from cad.confirmations.requirements import Requirements
from cad.records.roots import Roots


def kinds(roots: Roots) -> Kinds:
    """Every kind of item the confirmation page asks about, in page order."""
    return {"requirements": Requirements(roots)}

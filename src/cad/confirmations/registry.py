from cad.confirmations.agent_checks import AgentChecks
from cad.confirmations.context_parts import ContextParts
from cad.confirmations.items import Kinds
from cad.confirmations.requirements import Requirements
from cad.records.roots import Roots


def kinds(roots: Roots) -> Kinds:
    return {
        "requirements": Requirements(roots),
        "context_part": ContextParts(roots),
        "agent_check": AgentChecks(roots),
    }

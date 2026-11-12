from pathlib import Path
from typing import Final, Literal

from cad.agent_checks import runs, verdicts
from cad.agent_checks.formula import GRAMMAR
from cad.agent_checks.model import UNITS, CheckDraft
from cad.agent_checks.runs import GeometryRun
from cad.agent_checks.store import StoredCheck, find
from cad.agent_checks.write import write_check
from cad.briefs import store as briefs
from cad.briefs.model import AgentLimit
from cad.briefs.store import ConfirmedSet
from cad.confirmations import agent_checks as confirming
from cad.frozen import Frozen
from cad.operations.model import Audience, Input, Tenant, operation
from cad.records.roots import Roots
from cad.sandbox import image
from cad.scorecard.material import ReportedScorecard
from cad.scorecard.model import AgainstBrief
from cad.tables.materials import MaterialsTable
from cad.variants import entry

WRITE_CHECK = (
    "Write a check for a requirement the person stated that no team check decides, such as a "
    "snap-fit's strain or a pin's shear stress, before you build any variant of its brief: once "
    "the brief holds a variant, the server refuses. Pass the brief_id, the requirement_id of an "
    "unchecked requirement you proposed on it, and the check. title names it in a few words, "
    "and measures says in one or two plain sentences what it measures. formula is one "
    f"expression of {GRAMMAR}, which the server evaluates. inputs binds each name the formula "
    "reads to one of geometry:<name>, a value your geometry code reports; team:<check>:<measure>, "
    "a team check's measure, such as team:mass:volume or team:holes:hole_diameter:0; "
    "material:<field>, the variant's material value, such as material:elastic_modulus; or "
    "source:<name>, a constant from sources. geometry is build123d code that receives the "
    "stored part as part and calls report(name, value, unit) once for each geometry input. It "
    "runs in the sandbox, twice for each variant, once with the part turned and moved, and a "
    "check whose two answers differ decides nothing. Before the check is stored the server runs "
    "the code on four probe shapes of its own and on probe, optional build123d code that sets "
    "probe to one shape like the parts you will build, each plain and turned and moved. Code "
    "whose answers change with the turn, or that gives the same length on every shape, is "
    "refused: read lengths from the part's edges, faces or volume, not its bounding box. Each "
    "source is a constant: its name, value and unit, the URL of a "
    "public page that writes it, and the quote it is written in. limit gives the comparator, "
    "the unit of the person's number, and source when the page writes the limit too. example "
    "is a worked example from a public page: its url, the quote, the value of each input not "
    "bound to a source, and the result the page writes. The server fetches each page, checks "
    "that each quote is on it and that each number is written in its quote, and evaluates the "
    "formula on the example: it must give the page's result. The check must read a source or "
    "a material value: a bare geometry or team measure is refused. Units are "
    f"{', '.join(UNITS)}. A refusal names the first rule the check breaks and stores nothing. "
    "A stored check is frozen and never edited; write a new one instead. It decides nothing "
    "until the person approves it on the confirmation page."
)


class WriteCheckInput(Input):
    brief_id: str
    requirement_id: str
    check: CheckDraft


class CheckWritten(Frozen):
    status: Literal["stored"] = "stored"
    check_sha256: str
    number: int
    title: str
    next_step: str


def with_agent_checks(
    card: ReportedScorecard,
    roots: Roots,
    variants: Path,
    confirmed: ConfirmedSet | None,
    table: MaterialsTable,
    *,
    run: bool,
) -> ReportedScorecard:
    """The card with each confirmed agent_limit whose check the person approved decided by that
    check. With `run`, the check's geometry code runs on the scored part first; a card read
    later shows what that run found."""
    basis = card.basis
    if confirmed is None or not isinstance(basis, AgainstBrief):
        return card
    project = briefs.read_brief(roots, confirmed.brief_id).project
    approved = [
        verdicts.Approved(requirement, requirement.target, stored)
        for requirement in confirmed.requirements
        if isinstance(requirement.target, AgentLimit)
        and (stored := find(roots.projects, project, requirement.target.check_sha256))
        and confirming.outcome(roots, project, stored) == "confirmed"
    ]
    if not approved:
        return card
    if run:
        brep = entry.open_entry(variants, card.variant_id, image.image_tag(image.BUILD)).brep
        stored = [one.stored for one in approved]
        verdicts.run_geometry(roots.projects, project, brep, card.brep_sha256, stored)

    def geometry(stored: StoredCheck) -> GeometryRun | None:
        return runs.read(roots.projects, project, verdicts.version(stored), card.brep_sha256)

    material = table.get_material(card.material_key)
    judged = verdicts.judged(basis, approved, card.results, material, geometry)
    return card.model_copy(update={"basis": judged})


def write_check_operation(tenant: Tenant, arguments: WriteCheckInput) -> CheckWritten:
    stored = write_check(
        tenant.roots, arguments.brief_id, arguments.requirement_id, arguments.check
    )
    return CheckWritten(
        check_sha256=stored.sha256,
        number=stored.number,
        title=stored.check.title,
        next_step=(
            "The check is frozen. Propose its requirement again as agent_limit with this "
            "check_sha256, the comparator and the person's limit, with every requirement that "
            "stays in force, then call ask_to_confirm: the person approves the check on the "
            "same page. It decides nothing until they do, and a variant's verdict on it is "
            "labelled as an agent-written check they approved, not reviewed by our team."
        ),
    )


OPERATIONS: Final = (
    operation(
        name="write_check",
        audience=Audience.AGENT,
        description=WRITE_CHECK,
        input=WriteCheckInput,
        output=CheckWritten,
        run=write_check_operation,
    ),
)

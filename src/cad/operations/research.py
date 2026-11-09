from typing import Annotated, Final

from pydantic import Field

from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.operations.model import Audience, Input, Tenant, operation
from cad.projects.model import ProjectRefused
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.research.fields import MAX_QUOTE_LENGTH
from cad.research.fields import Field as MaterialField
from cad.research.overlay import ProjectTable, project_table
from cad.research.requests import SUBMIT, requests_on
from cad.research.submit import Question, ResearchAnswer, ResearchRefused, submit
from cad.sandbox import host
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.material import ReportedScorecard
from cad.tables.materials import KEY_PATTERN

SUBMIT_RESEARCH = (
    "Answer a research request from a score_variant card or a propose_requirements reply. "
    "Pass the request's brief_id, key and field; the value and its unit as the page writes "
    'them, such as 0.36 with unit "" for a Poisson\'s ratio or 3.5 with unit "GPa"; the URL '
    "of a public https page that states the value; and the quote you read it from, copied "
    'from that page, such as "the Poisson ratio = 0.36" or a table row. The server fetches '
    "the page, checks that the quote is on it and that the value is written in the quote, "
    "converts your unit, and stores the page as the value's citation. Spacing, punctuation, "
    "markup and case in the quote may differ from the page; its words and numbers may not. "
    "A source for a near material, such as generic PLA for a PLA brand, is allowed. accepted "
    "means the brief's project now has a researched value for that field, and only that "
    "project. refused gives the reason and, when another page could answer, a new request: "
    "fix what the reason names or find another source and submit again. A field the table "
    "already cites is never replaced. Then call score_variant again with the same arguments: "
    "a result that reads the value is labelled researched, and you report a pass on it as "
    '"passes on researched data", naming the source and quote.'
)


def brief_table(roots: Roots, brief_id: str | None) -> ProjectTable:
    git = host.materials_table()
    if brief_id is None:
        return ProjectTable(git)
    project = briefs.read_brief(roots, brief_id).project
    return project_table(git, roots.projects, project)


def with_research(
    card: ReportedScorecard, table: ProjectTable, brief_id: str | None
) -> ReportedScorecard:
    if table.problem is not None:
        return card.model_copy(update={"research_problem": table.problem})
    research = requests_on(card.results, card.material_key, table.table, brief_id, table.dropped)
    return card.model_copy(update={"research": research}) if research else card


class SubmitResearchInput(Input):
    brief_id: str
    key: Annotated[str, Field(pattern=f"^{KEY_PATTERN.pattern}$")]
    field: MaterialField
    value: float
    unit: Annotated[str, Field(max_length=32)]
    url: Annotated[str, Field(max_length=2048)]
    quote: Annotated[str, Field(min_length=1, max_length=MAX_QUOTE_LENGTH)]


def submit_research(tenant: Tenant, arguments: SubmitResearchInput) -> ResearchAnswer:
    roots = tenant.roots
    try:
        project = briefs.read_brief(roots, arguments.brief_id).project
        table = host.materials_table()
        question = Question(
            arguments.brief_id,
            project,
            table.row_key(arguments.key),
            arguments.field,
            arguments.value,
            arguments.unit,
            arguments.url,
            arguments.quote,
        )
        return submit(table, roots.projects, question)
    except (BriefRefused, ProjectRefused, SandboxUnavailable, StoreUnusable) as error:
        return ResearchRefused(
            key=arguments.key,
            field=arguments.field,
            reason=f"{type(error).__name__}: {error}",
        )


OPERATIONS: Final = (
    operation(
        name=SUBMIT,
        audience=Audience.AGENT,
        description=SUBMIT_RESEARCH,
        input=SubmitResearchInput,
        output=ResearchAnswer,
        run=submit_research,
    ),
)

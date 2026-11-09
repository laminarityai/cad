from typing import Annotated

from mcp.server.mcpserver.tools import Tool
from pydantic import Field

from cad.briefs import store as briefs
from cad.briefs.store import BriefRefused
from cad.projects.model import ProjectRefused
from cad.records.roots import Roots
from cad.records.signed import StoreUnusable
from cad.research.fetch import fetch
from cad.research.overlay import ProjectTable, project_table
from cad.research.requests import SUBMIT, requests_on
from cad.research.submit import Fetch, Question, ResearchAnswer, ResearchRefused, submit
from cad.sandbox import host
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.material import ReportedScorecard
from cad.sources.fields import MAX_QUOTE_LENGTH
from cad.sources.fields import Field as MaterialField
from cad.tables.materials import KEY_PATTERN

SUBMIT_RESEARCH = (
    "Answer a research request from a score_variant card or a propose_requirements reply. "
    "Pass the request's brief_id, key and field, the URL of a public https page that states "
    "the value, and a quote copied word for word from that page, naming the property and "
    "giving one value with its unit, such as "
    '"Poisson\'s ratio 0.36" or "Tensile modulus 3.5 GPa". Never pass a number of your own: '
    "the server fetches the page, checks that the quote is on it and reads the value itself. "
    "A source for a near material, such as generic PLA for a PLA brand, is allowed. accepted "
    "means the brief's project now has a researched value for that field, and only that "
    "project. refused gives the reason and, when another page could answer, a new request: "
    "find another source and submit again. A field the table already cites is never replaced. "
    "Then call score_variant again with the same arguments: a result that reads the value is "
    'labelled researched, and you report a pass on it as "passes on researched data", naming '
    "the source and quote."
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


def research_tools(roots: Roots, fetcher: Fetch = fetch) -> list[Tool]:
    def submit_research(
        brief_id: str,
        key: Annotated[str, Field(pattern=f"^{KEY_PATTERN.pattern}$")],
        field: MaterialField,
        url: Annotated[str, Field(max_length=2048)],
        quote: Annotated[str, Field(min_length=1, max_length=MAX_QUOTE_LENGTH)],
    ) -> ResearchAnswer:
        try:
            project = briefs.read_brief(roots, brief_id).project
            table = host.materials_table()
            question = Question(brief_id, project, table.row_key(key), field, url, quote)
            return submit(table, roots.projects, question, fetcher=fetcher)
        except (BriefRefused, ProjectRefused, SandboxUnavailable, StoreUnusable) as error:
            return ResearchRefused(key=key, field=field, reason=f"{type(error).__name__}: {error}")

    return [Tool.from_function(submit_research, name=SUBMIT, description=SUBMIT_RESEARCH)]

"""The knowledge base search tool. It returns pointers and quotes, never a value a check reads."""

from functools import cache
from typing import Annotated, Final

from pydantic import BaseModel, Field

from cad.knowledge.corpus import load
from cad.knowledge.search import Index
from cad.operations.model import BOTH, Input, Tenant, operation

MAX_QUERY_CHARS: Final = 500
MAX_K: Final = 20
SEARCH_KNOWLEDGE = (
    "Search the knowledge base of cited sources (data sheets, standards, reports) by keywords. "
    "Returns up to k sections, best first, each with its subject, source title, url, page, "
    "section and quoted text. Results are possible matches ranked by keyword overlap, not checked "
    "for identity. Read each subject and quote, and use only a result about exactly the "
    "material or part the user means. When no result is about it, look for the material in "
    "list_materials. Cite the source and page you use. No check reads a "
    "number from a result. To fill a value a check needs, answer the research request on the "
    "scorecard or proposal with submit_research, giving the result's url and a quote from that "
    "page."
)


class KnowledgeHit(BaseModel):
    id: str
    subject: str
    title: str
    section: str
    page: str | None
    url: str
    retrieved: str
    text: str


class KnowledgeHits(BaseModel):
    hits: list[KnowledgeHit]


class SearchKnowledgeInput(Input):
    query: Annotated[str, Field(max_length=MAX_QUERY_CHARS)]
    k: Annotated[int, Field(ge=1, le=MAX_K)] = 5


@cache
def _index() -> Index:
    return Index(load())


def search_knowledge(tenant: Tenant, arguments: SearchKnowledgeInput) -> KnowledgeHits:
    del tenant
    return KnowledgeHits(
        hits=[
            KnowledgeHit(
                id=hit.pointer.id,
                subject=hit.subject,
                title=hit.pointer.title,
                section=hit.pointer.section,
                page=hit.pointer.page,
                url=hit.pointer.url,
                retrieved=hit.pointer.retrieved.isoformat(),
                text=hit.text,
            )
            for hit in _index().search(arguments.query, arguments.k)
        ]
    )


OPERATIONS: Final = (
    operation(
        name="search_knowledge",
        audience=BOTH,
        description=SEARCH_KNOWLEDGE,
        input=SearchKnowledgeInput,
        output=KnowledgeHits,
        run=search_knowledge,
    ),
)

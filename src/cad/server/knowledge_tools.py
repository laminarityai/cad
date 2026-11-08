"""The knowledge base search tool. It returns pointers and quotes, never a value a check reads."""

from typing import Annotated, Final

from mcp.server.mcpserver.tools import Tool
from pydantic import BaseModel, Field

from cad.knowledge.corpus import load
from cad.knowledge.search import Index

MAX_QUERY_CHARS: Final = 500
MAX_K: Final = 20
SEARCH_KNOWLEDGE = (
    "Search the knowledge base of cited sources (data sheets, standards, reports) by keywords. "
    "Returns up to k sections, best first, each with its subject, source title, url, page, "
    "section and quoted text. Results are candidates ranked by keyword overlap, not checked "
    "for identity. Read each subject and quote, and use only a result about exactly the "
    "material or part the user means. Cite the source and page you use. A number from a result "
    "is never checked until the user confirms it as a candidate value."
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


def knowledge_tools() -> tuple[Tool, ...]:
    index = Index(load())

    def search_knowledge(
        query: Annotated[str, Field(max_length=MAX_QUERY_CHARS)],
        k: Annotated[int, Field(ge=1, le=MAX_K)] = 5,
    ) -> KnowledgeHits:
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
                for hit in index.search(query, k)
            ]
        )

    return (Tool.from_function(search_knowledge, description=SEARCH_KNOWLEDGE),)

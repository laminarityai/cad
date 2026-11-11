"""The confirmation card the web app draws in the project's chat. It holds what the page at
`/projects/<pid>/confirm` shows, sealed for the signed-in person the same way, and its answer
posts to that page's form handler."""

from pydantic import BaseModel

from cad.accounts.principal import PersonSession
from cad.confirmations import snapshot
from cad.confirmations.answers import ItemKindName
from cad.confirmations.items import pending
from cad.confirmations.registry import kinds
from cad.operations.model import Tenant
from cad.projects.model import ProjectId


class CardEditable(BaseModel):
    row: str
    placeholder: str


class CardRow(BaseModel):
    headline: str
    quote: str
    editable: CardEditable | None


class CardItem(BaseModel):
    kind: ItemKindName
    brief_id: str
    title: str
    brief_text: str
    rows: tuple[CardRow, ...]


class ConfirmationCard(BaseModel):
    """`snapshot` goes back with the answer. It is null, and `items` empty, when nothing waits."""

    snapshot: str | None
    items: tuple[CardItem, ...]


class ProjectArguments(BaseModel):
    project_id: str


def card(person: PersonSession, tenant: Tenant, project: ProjectId) -> ConfirmationCard:
    every = kinds(tenant.roots)
    refs = pending(every, project)
    if not refs:
        return ConfirmationCard(snapshot=None, items=())
    sealed = snapshot.seal(tenant.roots.projects, person, project, refs)
    items: list[CardItem] = []
    for ref in refs:
        section = every[ref.kind].section(ref)
        rows = tuple(
            CardRow(
                headline=row.headline,
                quote=row.quote,
                editable=None
                if row.editable is None
                else CardEditable(row=row.editable.row, placeholder=row.editable.placeholder),
            )
            for row in section.rows
        )
        items.append(
            CardItem(
                kind=ref.kind,
                brief_id=section.brief_id,
                title=section.title,
                brief_text=section.context,
                rows=rows,
            )
        )
    return ConfirmationCard(snapshot=sealed, items=tuple(items))

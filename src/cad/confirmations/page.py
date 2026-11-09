import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from urllib.parse import parse_qs

from cad.accounts.principal import PersonSession
from cad.briefs.model import MAX_NOTE_CHARS
from cad.confirmations.answers import (
    MAX_EDIT_CHARS,
    Edit,
    ItemAnswer,
    ItemRef,
    PageAnswer,
    append_answer,
    read_ledger,
)
from cad.confirmations.items import Changes, Editable, Kinds, Refused, Section, pending
from cad.projects.model import ProjectId
from cad.records.roots import Roots

EDIT: Final = re.compile(r"edit-(0|[1-9][0-9]{0,3})-([0-9a-f]{16})")
DECLINE_EDITS: Final = (
    "You changed a number on an item you declined. A change is kept only when you confirm "
    "that item. Go back and confirm it, or clear the change."
)
DECLINE: Final = re.compile(r"decline-(0|[1-9][0-9]{0,3})")
SNAPSHOT: Final = "snapshot"
STYLE: Final = (
    "body{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;"
    "color:#1d1d1f;background:#fafafa}"
    "h1{font-size:1.6rem;margin-bottom:.25rem}.lead{color:#444;margin-top:0}"
    ".item{background:#fff;border:1px solid #ddd;border-radius:8px;padding:.5rem 1.25rem;"
    "margin:1.25rem 0}.item h2{font-size:1.1rem}"
    "blockquote{white-space:pre-wrap;border-left:4px solid #888;margin:0;padding:.5rem 1rem;"
    "background:#f4f4f4}"
    ".check{color:#555}li{margin:.75rem 0}textarea{width:100%;min-height:4rem}"
    ".change input{font-size:1rem;margin-left:.5rem;padding:.25rem .5rem;width:14rem}"
    "button{font-size:1rem;margin:.5rem .5rem 0 0;padding:.5rem 1.25rem;border-radius:6px;"
    "border:1px solid #888;background:#fff}button[value=confirm]{background:#1d6f42;color:#fff;"
    "border-color:#1d6f42}.decline{margin:-.75rem 0 1.25rem 1.25rem}"
)


@dataclass(frozen=True, slots=True)
class Form:
    answer: Literal["confirm", "decline"]
    note: str
    edits: Mapping[int, tuple[Edit, ...]]
    declined: frozenset[int]


@dataclass(frozen=True, slots=True)
class Recorded:
    confirmed: int
    declined: int


@dataclass(frozen=True, slots=True)
class AlreadyAnswered:
    pass


@dataclass(frozen=True, slots=True)
class Changed:
    pass


def sealed_snapshot(body: bytes) -> str | None:
    fields = _fields(body)
    found = None if fields is None else fields.get(SNAPSHOT, [])
    return found[0] if found is not None and len(found) == 1 else None


def _fields(body: bytes) -> dict[str, list[str]] | None:
    try:
        return parse_qs(body.decode(), keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        return None


def parse_form(body: bytes, size: int) -> Form | None:
    """The answer the form gives. Its snapshot is read apart, by `sealed_snapshot`."""
    fields = _fields(body)
    if fields is None:
        return None
    fields.pop(SNAPSHOT, None)
    answers = fields.pop("answer", [])
    notes = fields.pop("note", [""])
    if len(answers) != 1 or len(notes) != 1 or len(notes[0]) > MAX_NOTE_CHARS:
        return None
    answer = answers[0]
    declined = _declined(fields, size)
    if (answer != "confirm" and answer != "decline") or declined is None:
        return None
    edits: dict[int, list[Edit]] = {}
    for name, values in fields.items():
        match = EDIT.fullmatch(name)
        if match is None or len(values) != 1 or len(values[0]) > MAX_EDIT_CHARS:
            return None
        index = int(match.group(1))
        if index >= size:
            return None
        if values[0].strip():
            edits.setdefault(index, []).append(Edit(row=match.group(2), text=values[0]))
    edited = {index: tuple(found) for index, found in edits.items()}
    return Form(answer, notes[0], edited, declined)


def _declined(fields: dict[str, list[str]], size: int) -> frozenset[int] | None:
    """Pop each `decline-<index>=decline` field: the items declined while the rest are confirmed."""
    found: set[int] = set()
    for name in list(fields):
        match = DECLINE.fullmatch(name)
        if match is None:
            continue
        index = int(match.group(1))
        if fields.pop(name) != ["decline"] or index >= size or not _declinable(size):
            return None
        found.add(index)
    return frozenset(found)


def _declinable(size: int) -> bool:
    """A page of one item shows no Decline box, because its Decline all button does the same."""
    return size > 1


def _verdict_of(form: Form, index: int) -> Literal["confirmed", "declined"]:
    declined = form.answer == "decline" or index in form.declined
    return "declined" if declined else "confirmed"


def read_edits(kinds: Kinds, items: Sequence[ItemRef], form: Form) -> Refused | Changes:
    """What the form's edits change, or why the page refuses them. A long page names the item."""
    if any(_verdict_of(form, index) == "declined" for index in form.edits):
        return Refused(DECLINE_EDITS)
    changes: list[str] = []
    for index, edits in sorted(form.edits.items()):
        ref = items[index]
        read = kinds[ref.kind].edit(ref, edits)
        where = f"{_label(index)}. " if len(items) > 1 else ""
        if isinstance(read, Refused):
            return Refused(where + read.message)
        changes.extend(where + change for change in read)
    return tuple(changes)


def _label(index: int) -> str:
    return f"Item {index + 1}"


def view(kinds: Kinds, project: ProjectId, items: Sequence[ItemRef], snapshot: str) -> bytes:
    sections = [kinds[ref.kind].section(ref) for ref in items]
    return render(sections, f"/projects/{project}/confirm", snapshot)


def answer_page(
    roots: Roots,
    kinds: Kinds,
    project: ProjectId,
    items: tuple[ItemRef, ...],
    form: Form,
    person: PersonSession,
    now: datetime,
) -> Recorded | AlreadyAnswered | Changed:
    ledger = read_ledger(roots.projects, project)
    if any(ledger.of(ref) is not None for ref in items):
        return AlreadyAnswered()
    if pending(kinds, project) != items:
        return Changed()
    answer = PageAnswer(
        project=project,
        answers=tuple(
            ItemAnswer(item=ref, verdict=_verdict_of(form, index), edits=form.edits.get(index, ()))
            for index, ref in enumerate(items)
        ),
        note=form.note,
        decided_at=now,
        account=person.account,
        session_id=person.session_id,
    )
    if not append_answer(roots.projects, project, answer):
        return AlreadyAnswered()
    verdicts = [item.verdict for item in answer.answers]
    return Recorded(verdicts.count("confirmed"), verdicts.count("declined"))


def render(sections: Sequence[Section], action: str, snapshot: str) -> bytes:
    each = _declinable(len(sections))
    items = "".join(
        _section(f"{_label(index)}. " if each else "", index, section)
        + (_decline_control(index) if each else "")
        for index, section in enumerate(sections)
    )
    count = "this item" if len(sections) == 1 else f"all {len(sections)} items"
    pick = " Tick Decline on any item that is wrong, and Confirm answers the rest." if each else ""
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<title>Confirm what the agent proposed</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>Confirm what the agent proposed</h1>"
        f'<p class="lead">One click answers {count} on this page. If a number is wrong, type '
        f"the right one beside it. Checks will read these numbers.{pick}</p>"
        f"{items}"
        f'<form id="page" method="post" action="{html.escape(action)}">'
        f'<input type="hidden" name="{SNAPSHOT}" value="{html.escape(snapshot)}">'
        '<label for="note">Note to the agent, if you decline</label>'
        f'<textarea id="note" name="note" maxlength="{MAX_NOTE_CHARS}"></textarea>'
        '<button name="answer" value="confirm">Confirm</button>'
        '<button name="answer" value="decline">Decline all</button>'
        "</form></body></html>"
    ).encode()


def _decline_control(index: int) -> str:
    return (
        f'<p class="decline"><label><input type="checkbox" form="page" name="decline-{index}" '
        'value="decline"> Decline this item</label></p>'
    )


def plain(message: str, *more: str) -> bytes:
    paragraphs = "".join(f"<p>{html.escape(one)}</p>" for one in (message, *more))
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Confirmation</title>"
        f"<style>{STYLE}</style></head><body>{paragraphs}</body></html>"
    ).encode()


def _section(label: str, index: int, section: Section) -> str:
    rows = "".join(
        f"<li><strong>{html.escape(row.headline)}</strong><br>"
        f'From your words: <q class="origin">{html.escape(row.quote)}</q><br>'
        f'<span class="check">{html.escape(row.decides)}</span>'
        f"{_change(index, row.editable)}</li>"
        for row in section.rows
    )
    return (
        f'<section class="item"><h2>{html.escape(label + section.title)}</h2>'
        f'<blockquote class="brief">{html.escape(section.context)}</blockquote>'
        f"<ol>{rows}</ol></section>"
    )


def _change(index: int, editable: Editable | None) -> str:
    """An empty field: a blank one is no edit, so the proposal stands unless the person types."""
    if editable is None:
        return ""
    return (
        '<br><label class="change">Change to'
        f'<input name="edit-{index}-{html.escape(editable.row)}" '
        f'placeholder="{html.escape(editable.placeholder)}" maxlength="{MAX_EDIT_CHARS}" '
        'form="page" autocomplete="off"></label>'
    )

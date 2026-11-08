import html
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from urllib.parse import parse_qs

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
from cad.confirmations.ballot import Ballot
from cad.confirmations.items import Editable, Kinds, Section, pending
from cad.records.roots import Roots

EDIT: Final = re.compile(r"edit-(0|[1-9][0-9]{0,3})-([0-9a-f]{16})")
DECLINE_EDITS: Final = (
    "You changed a number and declined. A change is kept only when you confirm. "
    "Go back and confirm, or clear the change and decline."
)
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
    "border-color:#1d6f42}"
)


@dataclass(frozen=True, slots=True)
class Form:
    answer: Literal["confirm", "decline"]
    note: str
    edits: Mapping[int, tuple[Edit, ...]]


@dataclass(frozen=True, slots=True)
class Recorded:
    verdict: Literal["confirmed", "declined"]


@dataclass(frozen=True, slots=True)
class AlreadyAnswered:
    pass


@dataclass(frozen=True, slots=True)
class Changed:
    pass


def parse_form(body: bytes, size: int) -> Form | None:
    try:
        fields = parse_qs(body.decode(), keep_blank_values=True, strict_parsing=True)
    except (UnicodeDecodeError, ValueError):
        return None
    answers = fields.pop("answer", [])
    notes = fields.pop("note", [""])
    if len(answers) != 1 or len(notes) != 1 or len(notes[0]) > MAX_NOTE_CHARS:
        return None
    answer = answers[0]
    if answer != "confirm" and answer != "decline":
        return None
    edits: dict[int, list[Edit]] = {}
    for name, values in fields.items():
        match = EDIT.fullmatch(name)
        if match is None or len(values) != 1 or len(values[0]) > MAX_EDIT_CHARS:
            return None
        index = int(match.group(1))
        if index >= size:
            return None
        if values[0]:
            edits.setdefault(index, []).append(Edit(row=match.group(2), text=values[0]))
    return Form(answer, notes[0], {index: tuple(found) for index, found in edits.items()})


def refused_edits(kinds: Kinds, items: Sequence[ItemRef], form: Form) -> str | None:
    if form.answer == "decline" and form.edits:
        return DECLINE_EDITS
    for index, edits in sorted(form.edits.items()):
        ref = items[index]
        message = kinds[ref.kind].edit(ref, edits)
        if message is not None:
            return message
    return None


def view(kinds: Kinds, ballot: Ballot) -> bytes | Changed:
    if pending(kinds, ballot.project) != ballot.items:
        return Changed()
    sections = [kinds[ref.kind].section(ref) for ref in ballot.items]
    return render(sections, f"/confirm/{ballot.token}")


def answer_page(
    roots: Roots, kinds: Kinds, ballot: Ballot, form: Form, now: datetime
) -> Recorded | AlreadyAnswered | Changed:
    ledger = read_ledger(roots.projects, ballot.project)
    if any(ledger.of(ref) is not None for ref in ballot.items):
        return AlreadyAnswered()
    if pending(kinds, ballot.project) != ballot.items:
        return Changed()
    verdict: Literal["confirmed", "declined"] = (
        "confirmed" if form.answer == "confirm" else "declined"
    )
    answer = PageAnswer(
        project=ballot.project,
        answers=tuple(
            ItemAnswer(item=ref, verdict=verdict, edits=form.edits.get(index, ()))
            for index, ref in enumerate(ballot.items)
        ),
        note=form.note,
        decided_at=now,
    )
    if not append_answer(roots.projects, ballot.project, answer):
        return AlreadyAnswered()
    return Recorded(verdict)


def render(sections: Sequence[Section], action: str) -> bytes:
    items = "".join(_section(index, section) for index, section in enumerate(sections))
    count = "this item" if len(sections) == 1 else f"all {len(sections)} items"
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<title>Confirm what the agent proposed</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>Confirm what the agent proposed</h1>"
        f'<p class="lead">One click answers {count} on this page. If a number is wrong, type '
        "the right one beside it, then confirm. Checks will read these numbers.</p>"
        f'<form method="post" action="{html.escape(action)}">'
        f"{items}"
        '<label for="note">Note to the agent, if you decline</label>'
        f'<textarea id="note" name="note" maxlength="{MAX_NOTE_CHARS}"></textarea>'
        '<button name="answer" value="confirm">Confirm all</button>'
        '<button name="answer" value="decline">Decline all</button>'
        "</form></body></html>"
    ).encode()


def plain(message: str) -> bytes:
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8><title>Confirmation</title>"
        f"<style>{STYLE}</style></head><body><p>{html.escape(message)}</p></body></html>"
    ).encode()


def _section(index: int, section: Section) -> str:
    rows = "".join(
        f"<li><strong>{html.escape(row.headline)}</strong><br>"
        f'From your words: <q class="origin">{html.escape(row.quote)}</q><br>'
        f'<span class="check">{html.escape(row.decides)}</span>'
        f"{_change(index, row.editable)}</li>"
        for row in section.rows
    )
    return (
        f'<section class="item"><h2>{html.escape(section.title)}</h2>'
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
        'autocomplete="off"></label>'
    )

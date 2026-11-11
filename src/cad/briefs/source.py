"""Whose words a brief holds. In chat the server copies them from the person's own messages, so
the agent never writes a brief's words there. An outside client has no transcript to copy from,
so it passes them."""

from cad.briefs.said import Words
from cad.briefs.store import BriefRefused
from cad.chat.log import person_said
from cad.operations.model import Tenant

CHAT_FIX = (
    "copy the words exactly from the brief or from one of the person's messages in this "
    "conversation; never quote words the person did not say"
)
OUTSIDE_FIX = "copy the words exactly from the brief, or pass the person's new words as said"


class WordsRefused(BriefRefused):
    pass


def first_words(tenant: Tenant, given: str | None) -> tuple[str, int | None]:
    """create_brief's text and the transcript seq it was copied from."""
    if tenant.conversation is None:
        if given is None:
            raise WordsRefused("pass text: the person's words, verbatim")
        return given, None
    if given is not None:
        raise WordsRefused(
            "in chat pass no text: the server copies the person's newest message into the brief"
        )
    said = person_said(tenant.conversations, tenant.conversation)
    if not said:
        raise WordsRefused("the person has said nothing in this conversation yet")
    seq, text = said[-1]
    return text, seq


def later_words(tenant: Tenant, given: str | None) -> Words:
    """Where propose_requirements may find a quote the brief does not hold yet."""
    if tenant.conversation is None:
        return Words(candidates=() if given is None else ((None, given),), fix=OUTSIDE_FIX)
    if given is not None:
        raise WordsRefused(
            "in chat pass no said: the server finds the words a quote comes from in the "
            "person's messages"
        )
    said = person_said(tenant.conversations, tenant.conversation)
    return Words(candidates=tuple(reversed(said)), fix=CHAT_FIX)

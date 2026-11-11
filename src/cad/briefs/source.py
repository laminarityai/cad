from cad.briefs.said import Spoken, Words
from cad.briefs.store import BriefRefused
from cad.chat.log import person_said
from cad.operations.model import Tenant

CHAT_HINT = (
    "copy the words exactly from the brief or from one of the person's messages in this "
    "conversation; never quote words the person did not say"
)
OUTSIDE_HINT = "copy the words exactly from the brief, or pass the person's new words as said"


class WordsRefused(BriefRefused):
    pass


def first_words(tenant: Tenant, given: str | None) -> Spoken:
    if tenant.conversation is None:
        if given is None:
            raise WordsRefused("pass text: the person's words, verbatim")
        return Spoken(None, given)
    if given is not None:
        raise WordsRefused(
            "in chat pass no text: the server copies the person's newest message into the brief"
        )
    said = person_said(tenant.conversations, tenant.conversation)
    if not said:
        raise WordsRefused("the person has said nothing in this conversation yet")
    return Spoken(*said[-1])


def later_words(tenant: Tenant, given: str | None) -> Words:
    if tenant.conversation is None:
        heard = () if given is None else (Spoken(None, given),)
        return Words(newest_first=heard, refusal_hint=OUTSIDE_HINT)
    if given is not None:
        raise WordsRefused(
            "in chat pass no said: the server finds the words a quote comes from in the "
            "person's messages"
        )
    said = person_said(tenant.conversations, tenant.conversation)
    return Words(newest_first=tuple(Spoken(*one) for one in reversed(said)), refusal_hint=CHAT_HINT)

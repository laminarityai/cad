import re
from typing import Final, Literal, NewType

from cad.conversations.model import ConversationId
from cad.frozen import Frozen

AccountId = NewType("AccountId", str)

# A Clerk user id is `user_` and base62. The id names a directory, so it is checked here, at the
# boundary, and nowhere else.
ACCOUNT_ID: Final = re.compile(r"[A-Za-z0-9_]{1,64}")


class NotAnAccount(ValueError):
    pass


def account_id(raw: object) -> AccountId:
    if not isinstance(raw, str) or not ACCOUNT_ID.fullmatch(raw):
        raise NotAnAccount(f"{raw!r} is not an account id")
    return AccountId(raw)


class PersonSession(Frozen):
    """A person signed in to the web app, from a Clerk session token."""

    kind: Literal["person"] = "person"
    account: AccountId
    session_id: str


class AgentToken(Frozen):
    """An agent acting for an account, from a Clerk OAuth access token on `/mcp`."""

    kind: Literal["agent"] = "agent"
    account: AccountId
    token_id: str
    client_id: str
    conversation: ConversationId | None = None


type Principal = PersonSession | AgentToken

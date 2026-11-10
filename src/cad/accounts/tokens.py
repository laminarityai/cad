"""Verifying Clerk's tokens against the instance's keys, with no network call per request.

Each route accepts one kind of token by calling one method: `/mcp` calls only `agent`, and a web
route calls only `person`. The JOSE header `typ` names the kind. Clerk sets `at+jwt` (or
`application/at+jwt`) on a JWT OAuth access token and `JWT` on a session token. Clerk's Python
SDK reads only the `oat_` prefix of opaque tokens and would take a JWT OAuth access token for a
session token, so the check is ours.

The same code verifies the local issuer's tokens (`accounts/local.py`), so tests, the probe and
local development run the code that verifies production tokens.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from cad.accounts.principal import AgentToken, NotAnAccount, PersonSession, account_id
from cad.conversations.model import ConversationId, NotAConversation, conversation_id

ALGORITHMS: Final = ["RS256"]
LEEWAY_SECONDS: Final = 5
AGENT_TYPES: Final = frozenset({"at+jwt", "application/at+jwt"})
SESSION_TYPES: Final = frozenset({"jwt"})
AGENT_CLAIMS: Final = ["exp", "iat", "iss", "sub", "aud", "jti", "client_id"]
SESSION_CLAIMS: Final = ["exp", "iat", "iss", "sub", "sid"]

type Keys = Callable[[str], RSAPublicKey | None]


@dataclass(frozen=True, slots=True)
class Issuer:
    """`url` is the `iss` of every token: Clerk's Frontend API URL. `resource` is our `/mcp` URL,
    which an agent token's `aud` must include, as Clerk's MCP guide says to check. `origins` are
    the web app's origins, one of which a session token's `azp` must name when it has one."""

    url: str
    keys: Keys
    resource: str
    origins: frozenset[str]


@dataclass(frozen=True, slots=True)
class Verifier:
    issuer: Issuer

    def agent(self, token: str) -> AgentToken | None:
        claims = self._claims(token, AGENT_TYPES, AGENT_CLAIMS, self.issuer.resource)
        if claims is None or not isinstance(claims["client_id"], str):
            return None
        conversation: ConversationId | None = None
        if "conversation" in claims:
            try:
                conversation = conversation_id(claims["conversation"])
            except NotAConversation:
                return None
        return AgentToken(
            account=account_id(claims["sub"]),
            token_id=str(claims["jti"]),
            client_id=claims["client_id"],
            conversation=conversation,
        )

    def person(self, token: str) -> PersonSession | None:
        claims = self._claims(token, SESSION_TYPES, SESSION_CLAIMS, None)
        if claims is None or claims.get("azp", None) not in {None, *self.issuer.origins}:
            return None
        return PersonSession(account=account_id(claims["sub"]), session_id=str(claims["sid"]))

    def _claims(
        self, token: str, types: frozenset[str], required: list[str], audience: str | None
    ) -> Mapping[str, Any] | None:
        try:
            header = jwt.get_unverified_header(token)
            if str(header.get("typ", "")).lower() not in types:
                return None
            key = self.issuer.keys(str(header.get("kid", "")))
            if key is None:
                return None
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                issuer=self.issuer.url,
                audience=audience,
                leeway=LEEWAY_SECONDS,
                options={"require": required, "verify_aud": audience is not None},
            )
            account_id(claims["sub"])
        except (jwt.PyJWTError, NotAnAccount):
            return None
        return claims


def jwks_keys(url: str) -> Keys:
    """Keys from Clerk's `<Frontend API>/.well-known/jwks.json`. The client caches the key set,
    so a request makes no network call unless a new `kid` appears, as after a key rotation."""
    client = jwt.PyJWKClient(url, cache_keys=True, lifespan=3600, timeout=10)

    def keys(kid: str) -> RSAPublicKey | None:
        try:
            key = client.get_signing_key(kid).key
        except jwt.PyJWKClientError:
            return None
        return key if isinstance(key, RSAPublicKey) else None

    return keys
